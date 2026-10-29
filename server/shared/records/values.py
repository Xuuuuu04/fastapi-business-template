from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from shared.data.fields import FieldNote, notes_of

MAX_VALUE_TEXT = 120


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


def value_text(value: Any) -> str:
    if contains_secret(value):
        return "已写入（敏感字段，不记录内容）"
    if isinstance(value, BaseModel):
        text = value.model_dump_json()
    elif isinstance(value, datetime):
        text = value.isoformat()
    elif isinstance(value, Decimal):
        text = format(value, "f")
    else:
        text = str(value)
    return text if len(text) <= MAX_VALUE_TEXT else text[:MAX_VALUE_TEXT] + "……"


def contains_secret(value: Any, seen: set[int] | None = None) -> bool:
    seen = seen if seen is not None else set()
    identity = id(value)
    if identity in seen:
        return False
    seen.add(identity)
    if isinstance(value, BaseModel):
        notes = notes_of(type(value))
        return any(
            note.secret or contains_secret(getattr(value, name), seen)
            for name, note in notes.items()
        )
    if isinstance(value, dict):
        return any(
            contains_secret(key, seen) or contains_secret(item, seen) for key, item in value.items()
        )
    if isinstance(value, list | tuple | set | frozenset):
        return any(contains_secret(item, seen) for item in value)
    return False


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
