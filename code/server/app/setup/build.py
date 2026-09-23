"""
按请求组装受注册表约束的笔记业务。
接口只接收入口，业务与存储不需要知道监控实现。
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from service.notes import rules
from service.notes.needs import NoteRules, NoteStore
from service.notes.public import Notes
from service.notes.service import NoteService
from service.notes.store.sqlite import SqliteNotes
from shared.db.connect import connect
from shared.modules.registry import Registry


# 在单次请求中创建并释放受监控的模块实例。
@contextmanager
def notes(path: Path, registry: Registry) -> Iterator[Notes]:
    if not path.is_file():
        raise sqlite3.OperationalError("数据库未初始化")
    conn = connect(path)
    try:
        store = cast(NoteStore, registry.bind("notes", "note_store", SqliteNotes(conn)))
        policy = cast(NoteRules, registry.bind("notes", "note_rules", rules))
        service = NoteService(store, policy)
        yield cast(Notes, registry.bind("notes_api", "notes", service))
    finally:
        conn.close()
