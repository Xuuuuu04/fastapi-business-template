"""
检查笔记业务的输入规则。
纯函数测试不启动 HTTP 或数据库。
"""

import pytest

from service.notes.rules import clean
from service.notes.types import InvalidNote


# 验证标题整理和长度上限。
def test_clean() -> None:
    assert clean(" 标题 ", "正文") == "标题"
    assert clean("字" * 80, "字" * 5000) == "字" * 80


# 验证非法输入无法进入保存过程。
@pytest.mark.parametrize("title,body", [(" ", ""), ("字" * 81, ""), ("标题", "字" * 5001)])
def test_invalid(title: str, body: str) -> None:
    with pytest.raises(InvalidNote):
        clean(title, body)
