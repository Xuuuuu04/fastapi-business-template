"""
声明笔记业务需要的存储操作。
具体实现和测试替代实现遵守同一输入与返回约定。
"""

from contextlib import AbstractContextManager
from typing import Protocol

from service.notes.types import Note


class NoteRules(Protocol):
    # 整理标题并校验业务输入。
    def clean(self, title: str, body: str) -> str: ...


class NoteStore(Protocol):
    # 提供一个完整业务操作使用的事务。
    def transaction(self) -> AbstractContextManager[object]: ...

    # 返回总数及按编号倒序排列的一页笔记。
    def list(self, offset: int, limit: int) -> tuple[int, list[Note]]: ...

    # 读取一条笔记，缺失时返回空值。
    def get(self, note_id: int) -> Note | None: ...

    # 创建笔记，标题重复时抛出业务冲突。
    def create(self, title: str, body: str) -> Note: ...

    # 更新笔记，缺失或标题重复时抛出对应错误。
    def update(self, note_id: int, title: str, body: str) -> Note: ...

    # 删除笔记，缺失时抛出对应错误。
    def delete(self, note_id: int) -> None: ...
