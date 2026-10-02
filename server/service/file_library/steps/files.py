"""
文件管理流程的步骤：先处理文件内容，再保存或清理数据库记录。
"""

from service.file_library.data import (
    CleanResult,
    CleanWork,
    DeleteWork,
    FileMissing,
    GetWork,
    ListWork,
    SaveWork,
)
from service.file_library.store.contract import FileStore
from shared.public import Nothing, step


# 从临时区接收文件内容，生成正式存储键。
@step("保存文件内容", reads=["org_id", "temp_id"], writes=["staged"], rule="R-01")
async def prepare_file(data: SaveWork, store: FileStore) -> None:
    data.staged = await store.stage(data.org_id, data.temp_id)


# 在数据库中登记已经保存的文件。
@step("登记文件", reads=["staged"], writes=["result"], rule="R-01", saves=True)
async def save_file(data: SaveWork, store: FileStore) -> None:
    data.result = await store.save(data.staged)


# 检查组织后读取文件信息和存储键。
@step("读取文件", reads=["org_id", "file_id"], writes=["result"], rule="R-02")
async def read_file(data: GetWork, store: FileStore) -> None:
    found = await store.get(data.org_id, data.file_id)
    if found is None:
        raise FileMissing()
    data.result = found


# 分页列出指定组织中尚未删除的文件。
@step("查询文件", reads=["org_id", "offset", "limit"], writes=["result"], rule="R-02")
async def list_files(data: ListWork, store: FileStore) -> None:
    data.result = await store.list_files(data.org_id, data.offset, data.limit)


# 先标记删除，下载立即不可用。
@step("标记删除", reads=["org_id", "file_id"], writes=["result"], rule="R-03", saves=True)
async def delete_file(data: DeleteWork, store: FileStore) -> None:
    if not await store.mark_deleted(data.org_id, data.file_id):
        raise FileMissing()
    data.result = Nothing()


# 收集要删除的正式文件。
@step("查找待清理文件", writes=["pending", "orphans"], rule="R-03")
async def find_deleted(data: CleanWork, store: FileStore) -> None:
    data.pending = await store.pending()
    data.orphans = await store.orphaned()


# 删除正式存储中的文件，并清理过期临时上传。
@step(
    "清理文件内容",
    reads=["pending", "orphans"],
    writes=["deleted_ids", "temp_removed", "orphan_removed"],
    rule="R-03",
)
async def remove_objects(data: CleanWork, store: FileStore) -> None:
    data.deleted_ids, data.temp_removed, data.orphan_removed = await store.remove_objects(
        data.pending, data.orphans
    )


# 最后删除数据库中的记录；前面的对象删除可以安全重试。
@step(
    "清理文件记录",
    reads=["deleted_ids", "temp_removed", "orphan_removed"],
    writes=["result"],
    rule="R-03",
    saves=True,
)
async def delete_rows(data: CleanWork, store: FileStore) -> None:
    data.result = CleanResult(
        removed=await store.purge(data.deleted_ids),
        temp_removed=data.temp_removed,
        orphan_removed=data.orphan_removed,
    )
