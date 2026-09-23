"""
约束当前 SQLite 存储的可替换行为。
新增存储实现必须复用这些约定并扩充参数化实现。
"""

import pytest

from service.notes.store.sqlite import SqliteNotes
from service.notes.types import NoteMissing, TitleUsed
from shared.db.connect import connect
from shared.db.migrate import migrate


# 验证存储的缺失、冲突、排序和事务回滚约定。
def test_store_contract(tmp_path) -> None:
    path = tmp_path / "contract.db"
    migrate(path)
    conn = connect(path)
    store = SqliteNotes(conn)
    try:
        assert store.get(123) is None
        with store.transaction():
            first = store.create("第一条", "")
        with pytest.raises(TitleUsed), store.transaction():
            store.create("第二条", "")
            store.create("第一条", "")
        assert store.list(0, 10) == (1, [first])
        with pytest.raises(NoteMissing), store.transaction():
            store.update(123, "不存在", "")
        with store.transaction():
            second = store.create("第二条", "")
        assert store.list(0, 1) == (2, [second])
        with store.transaction():
            store.delete(first.id)
        assert store.get(first.id) is None
    finally:
        conn.close()
