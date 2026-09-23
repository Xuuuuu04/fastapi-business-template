"""
文件模块的数据访问和正式存储调用。查询始终限定组织；清理只允许系统调用者。
"""

import logging
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy import RowMapping, delete, insert, select, update

from service.file_library.data import FileEntry, FileList, FileStage, FileView, PendingFile
from service.file_library.store.tables import files
from shared.public import Caller, Db, ModuleFiles, NotAllowed

log = logging.getLogger("server.files")


class SqlFileStore:
    # 取得数据库、模块文件入口和经过验证的调用者。
    def __init__(self, db: Db, files: ModuleFiles, caller: Caller) -> None:
        self.db, self.files, self.caller = db, files, caller

    # 在组织范围内把临时文件保存到正式存储，形成待登记的元数据。
    async def stage(self, org_id: str, temp_id: str) -> FileStage:
        self.require_org(org_id)
        info = await self.files.upload_info(temp_id)
        file_id = secrets.token_hex(16)
        saved = await self.files.adopt(temp_id, f"{org_id}/{file_id}")
        return FileStage(
            id=file_id,
            org_id=org_id,
            name=info.name,
            size=saved.size,
            sha256=saved.sha256,
            content_type=info.content_type,
            key=saved.key,
        )

    # 插入文件记录；插入失败时尝试删除已经保存的文件。
    async def save(self, staged: FileStage) -> FileView:
        self.require_org(staged.org_id)
        now = datetime.now(UTC)
        statement = insert(files).values(
            id=staged.id,
            org_id=staged.org_id,
            name=staged.name,
            size=staged.size,
            sha256=staged.sha256,
            content_type=staged.content_type,
            storage_key=staged.key,
            created_at=now,
        )
        try:
            await self.db.change(statement)
        except Exception:
            try:
                await self.files.delete(staged.key)
            except Exception:
                log.exception("file_cleanup_failed file_id=%s", staged.id)
            raise
        return FileView(
            id=staged.id,
            org_id=staged.org_id,
            name=staged.name,
            size=staged.size,
            sha256=staged.sha256,
            content_type=staged.content_type,
            created_at=now,
        )

    # 按组织读取一个未删除的文件。
    async def get(self, org_id: str, file_id: str) -> FileEntry | None:
        self.require_org(org_id)
        row = await self.db.first(
            select(files).where(
                files.c.id == file_id, files.c.org_id == org_id, files.c.deleted_at.is_(None)
            )
        )
        return FileEntry(view=view_of(row), key=row["storage_key"]) if row else None

    # 只列出指定组织的未删除文件。
    async def list_files(self, org_id: str) -> FileList:
        self.require_org(org_id)
        rows = await self.db.all(
            select(files)
            .where(files.c.org_id == org_id, files.c.deleted_at.is_(None))
            .order_by(files.c.created_at.desc())
            .limit(200)
        )
        return FileList(items=[view_of(row) for row in rows])

    # 在数据库中标记删除，立即阻止读取和下载。
    async def mark_deleted(self, org_id: str, file_id: str) -> bool:
        self.require_org(org_id)
        count = await self.db.change(
            update(files)
            .where(
                files.c.id == file_id,
                files.c.org_id == org_id,
                files.c.deleted_at.is_(None),
            )
            .values(deleted_at=time.time())
        )
        return count > 0

    # 系统清理任务查找已删除但仍有正式存储内容的文件。
    async def pending(self) -> list[PendingFile]:
        self.require_system()
        rows = await self.db.all(
            select(files.c.id, files.c.storage_key)
            .where(files.c.deleted_at.is_not(None))
            .order_by(files.c.deleted_at)
            .limit(100)
        )
        return [PendingFile(id=row["id"], key=row["storage_key"]) for row in rows]

    # 找出超过一小时仍没有数据库记录的正式对象，单次最多清理一百个。
    async def orphaned(self) -> list[str]:
        self.require_system()
        old = time.time() - 3600
        batch: list[str] = []
        result: list[str] = []
        async for item in self.files.list_objects():
            if item.modified_at >= old:
                continue
            batch.append(item.key)
            if len(batch) >= 100:
                result.extend(await self.unrecorded(batch))
                batch.clear()
                if len(result) >= 100:
                    return result[:100]
        if batch:
            result.extend(await self.unrecorded(batch))
        return result[:100]

    # 一批存储键中，查出数据库没有记录的键。
    async def unrecorded(self, keys: list[str]) -> list[str]:
        rows = await self.db.all(select(files.c.storage_key).where(files.c.storage_key.in_(keys)))
        recorded = {row["storage_key"] for row in rows}
        return [key for key in keys if key not in recorded]

    # 先删除存储对象，再清理过期的临时上传；删除操作允许重试。
    async def remove_objects(
        self, pending: list[PendingFile], orphans: list[str]
    ) -> tuple[list[str], int, int]:
        self.require_system()
        removed = []
        for item in pending:
            await self.files.delete(item.key)
            removed.append(item.id)
        for key in orphans:
            await self.files.delete(key)
        return removed, await self.files.clean_uploads(3600), len(orphans)

    # 只删除已经从存储清理的记录。
    async def purge(self, ids: list[str]) -> int:
        self.require_system()
        if not ids:
            return 0
        return await self.db.change(
            delete(files).where(files.c.id.in_(ids), files.c.deleted_at.is_not(None))
        )

    # 不允许普通调用者访问其他组织，也不接受没有组织范围的身份。
    def require_org(self, org_id: str) -> None:
        if not org_id or (self.caller.org_id != "*" and self.caller.org_id != org_id):
            raise NotAllowed("不能访问指定组织的文件")

    # 清理任务必须以系统身份和全组织范围运行。
    def require_system(self) -> None:
        if self.caller.kind != "system" or self.caller.org_id != "*":
            raise NotAllowed("只有系统任务可以清理已删除文件")


# 把数据库行转换为不包含存储键的公开文件信息。
def view_of(row: RowMapping) -> FileView:
    return FileView(
        id=row["id"],
        org_id=row["org_id"],
        name=row["name"],
        size=int(row["size"]),
        sha256=row["sha256"],
        content_type=row["content_type"],
        created_at=row["created_at"],
    )
