"""
文件步骤的独立测试：不存在的文件、存储删除失败、已清理记录的统计。
只替换数据访问入口，仍使用框架的步骤读写检查。
"""

from unittest.mock import AsyncMock

import pytest

from service.file_library.data import CleanWork, DeleteWork, FileMissing, GetWork, PendingFile
from service.file_library.steps.files import delete_file, delete_rows, read_file, remove_objects
from service.file_library.store.contract import FileStore
from shared.flow.testing import try_step_async


# R-02、R-03：不存在的文件不能读取或删除，不能把没有找到当作成功。
@pytest.mark.anyio
async def test_missing_file_is_rejected() -> None:
    store = AsyncMock(spec=FileStore)
    store.get.return_value = None
    store.mark_deleted.return_value = False
    values = {"org_id": "north", "file_id": "missing"}
    with pytest.raises(FileMissing):
        await try_step_async(read_file, GetWork, values.copy(), store=store)
    with pytest.raises(FileMissing):
        await try_step_async(delete_file, DeleteWork, values.copy(), store=store)


# R-03：存储删除失败时必须报错，不生成可以删除数据库记录的成功结果。
@pytest.mark.anyio
async def test_storage_failure_keeps_cleanup_unfinished() -> None:
    store = AsyncMock(spec=FileStore)
    store.remove_objects.side_effect = OSError("storage unavailable")
    values = {"pending": [PendingFile(id="file-1", key="north/file-1")], "orphans": []}
    with pytest.raises(OSError, match="storage unavailable"):
        await try_step_async(remove_objects, CleanWork, values, store=store)
    assert "deleted_ids" not in values
    store.purge.assert_not_awaited()


# R-03：只清理存储已经删除的文件记录，临时文件与无记录对象分别统计。
@pytest.mark.anyio
async def test_cleanup_reports_confirmed_deletions() -> None:
    store = AsyncMock(spec=FileStore)
    store.purge.return_value = 2
    values = {"deleted_ids": ["file-1", "file-2"], "temp_removed": 3, "orphan_removed": 1}
    result = await try_step_async(delete_rows, CleanWork, values, store=store)
    store.purge.assert_awaited_once_with(["file-1", "file-2"])
    assert result.values["result"].model_dump() == {
        "removed": 2,
        "temp_removed": 3,
        "orphan_removed": 1,
    }
