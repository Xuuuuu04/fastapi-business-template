"""
处理笔记的查询与写入规则。
业务入口统一安排事务，不包含 SQL 和 HTTP 处理。
"""

from service.notes.needs import NoteRules, NoteStore
from service.notes.types import InvalidNote, Note, NoteMissing


class NoteService:
    # 接收已经组装好的存储实现。
    def __init__(self, store: NoteStore, rules: NoteRules) -> None:
        self.store = store
        self.rules = rules

    # 返回经过分页范围检查的笔记列表。
    def list(self, offset: int, limit: int) -> tuple[int, list[Note]]:
        if offset < 0 or not 1 <= limit <= 100:
            raise InvalidNote("分页范围不正确")
        return self.store.list(offset, limit)

    # 读取笔记并明确报告不存在的情况。
    def get(self, note_id: int) -> Note:
        note = self.store.get(note_id)
        if note is None:
            raise NoteMissing
        return note

    # 在同一事务内创建已校验的笔记。
    def create(self, title: str, body: str) -> Note:
        title = self.rules.clean(title, body)
        with self.store.transaction():
            return self.store.create(title, body)

    # 在同一事务内更新已校验的笔记。
    def update(self, note_id: int, title: str, body: str) -> Note:
        title = self.rules.clean(title, body)
        with self.store.transaction():
            return self.store.update(note_id, title, body)

    # 在同一事务内删除指定笔记。
    def delete(self, note_id: int) -> None:
        with self.store.transaction():
            self.store.delete(note_id)
