"""
隔离检查笔记服务的协作顺序和错误行为。
存储使用测试替身，不依赖 HTTP 或数据库。
"""

from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from service.notes import rules
from service.notes.needs import NoteStore
from service.notes.service import NoteService
from service.notes.types import InvalidNote, NoteMissing


# 验证校验后的标题传给存储并使用事务。
def test_create() -> None:
    store = Mock(spec=NoteStore)
    store.transaction.return_value = nullcontext()
    service = NoteService(store, rules)
    assert service.create(" 标题 ", "正文") is store.create.return_value
    store.transaction.assert_called_once_with()
    store.create.assert_called_once_with("标题", "正文")


# 验证非法输入不会开始事务或写入。
def test_no_write_on_invalid() -> None:
    store = Mock(spec=NoteStore)
    service = NoteService(store, rules)
    with pytest.raises(InvalidNote):
        service.create(" ", "")
    store.transaction.assert_not_called()
    store.create.assert_not_called()


# 验证查询缺失和非法分页转换为业务错误。
def test_read_errors() -> None:
    store = Mock(spec=NoteStore)
    store.get.return_value = None
    service = NoteService(store, rules)
    with pytest.raises(NoteMissing):
        service.get(123)
    with pytest.raises(InvalidNote):
        service.list(-1, 10)
    store.list.assert_not_called()
