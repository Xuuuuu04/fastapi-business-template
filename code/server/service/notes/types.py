"""
定义笔记业务的数据与错误。
本文件不依赖 HTTP 框架或数据库实现。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Note:
    id: int
    title: str
    body: str
    created_at: str


class NoteMissing(Exception):
    pass


class TitleUsed(Exception):
    pass


class InvalidNote(Exception):
    pass
