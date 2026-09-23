"""
声明笔记模块对外提供的操作。
接口层和其他业务只依赖此约定，不直接创建具体服务。
"""

from typing import Protocol

from service.notes.types import Note


class Notes(Protocol):
    # 查询一页笔记及总数。
    def list(self, offset: int, limit: int) -> tuple[int, list[Note]]: ...

    # 读取笔记，缺失时抛出 NoteMissing。
    def get(self, note_id: int) -> Note: ...

    # 创建笔记，校验失败或标题重复时抛出业务错误。
    def create(self, title: str, body: str) -> Note: ...

    # 更新笔记并返回完整记录。
    def update(self, note_id: int, title: str, body: str) -> Note: ...

    # 删除笔记，缺失时抛出 NoteMissing。
    def delete(self, note_id: int) -> None: ...
