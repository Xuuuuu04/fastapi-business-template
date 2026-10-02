"""
文件管理步骤使用的数据访问约定。
"""

from typing import Protocol

from service.file_library.data import FileEntry, FilePage, FileStage, FileView, PendingFile


# 文件步骤允许使用的数据访问操作，具体存储实现可单独替换。
class FileStore(Protocol):
    # 把临时上传放进正式存储。
    async def stage(self, org_id: str, temp_id: str) -> FileStage: ...

    # 登记文件元数据。
    async def save(self, staged: FileStage) -> FileView: ...

    # 按组织和文件编号读取。
    async def get(self, org_id: str, file_id: str) -> FileEntry | None: ...

    # 查询组织中未删除的文件。
    async def list_files(self, org_id: str, offset: int, limit: int) -> FilePage: ...

    # 标记文件为待清理。
    async def mark_deleted(self, org_id: str, file_id: str) -> bool: ...

    # 收集已删除的文件。
    async def pending(self) -> list[PendingFile]: ...

    # 找出超过一小时仍没有文件记录的正式对象。
    async def orphaned(self) -> list[str]: ...

    # 删除已标记对象和无记录对象，同时清理过期临时上传。
    async def remove_objects(
        self, pending: list[PendingFile], orphans: list[str]
    ) -> tuple[list[str], int, int]: ...

    # 删除已清理文件的数据库记录。
    async def purge(self, ids: list[str]) -> int: ...
