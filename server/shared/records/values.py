"""
把步骤写入的字段整理成一句安全的中文摘要。
默认只记录数量、长度这类形状信息；字段声明了 log_value=True 才记录取值，secret=True 的字段从不记录。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from shared.data.fields import FieldNote

MAX_VALUE_TEXT = 120


# 描述一个字段写入后的情况。
def describe_value(value: Any, note: FieldNote) -> str:
    label = note.meaning or note.name
    unit = note.unit if note.unit else ""
    if note.secret:
        return f"{label}：已写入（敏感字段，不记录内容）"
    if value is None:
        return f"{label}：空，表示{note.empty or '没有值'}"
    if note.log_value:
        return f"{label}：{value_text(value)}{unit}"
    return f"{label}：{shape_text(value)}"


# 把允许记录的取值转成短文本。
def value_text(value: Any) -> str:
    if isinstance(value, BaseModel):
        text = value.model_dump_json()
    elif isinstance(value, datetime):
        text = value.isoformat()
    elif isinstance(value, Decimal):
        text = format(value, "f")
    else:
        text = str(value)
    return text if len(text) <= MAX_VALUE_TEXT else text[:MAX_VALUE_TEXT] + "……"


# 只描述数据的形状，不暴露内容。
def shape_text(value: Any) -> str:
    if isinstance(value, bool):
        return "已写入是否标记"
    if isinstance(value, list | tuple | set | frozenset | dict):
        return f"{len(value)} 项"
    if isinstance(value, str):
        return f"文本 {len(value)} 字" if value else "空文本"
    if isinstance(value, int | float | Decimal):
        return "已写入数字"
    if isinstance(value, BaseModel):
        return f"已写入 {type(value).__name__}"
    return f"已写入 {type(value).__name__}"
