"""
定义字段说明的写法 meaning()，以及读取字段说明的方法。
每个字段都写中文含义；单位、规则编号、空值含义和是否记录取值也写在字段上，
接口文档、字段表、运行记录和字段来源图都从这里读取，不再另写一份。
"""

import types
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, Field
from pydantic_core import PydanticUndefined

NOTE_KEY = "x-note"


# 字段的业务含义、单位、规则与敏感性，用于文档和运行记录。
@dataclass(frozen=True)
class FieldNote:
    name: str
    meaning: str
    unit: str = ""
    rule: str = ""
    empty: str = ""
    log_value: bool = False
    secret: bool = False
    has_default: bool = False


# 声明字段的中文含义；可空字段用 empty 说明空值代表什么。
def meaning(
    text: str,
    *,
    unit: str = "",
    rule: str = "",
    empty: str = "",
    log_value: bool = False,
    secret: bool = False,
    default: Any = PydanticUndefined,
    default_factory: Any = None,
    example: Any = None,
    **limits: Any,
) -> Any:
    note: dict[str, object] = {"meaning": text, "unit": unit, "rule": rule, "empty": empty}
    note |= {"log_value": log_value, "secret": secret}
    options: dict[str, Any] = {"description": describe(text, unit, rule, empty)}
    options["json_schema_extra"] = {NOTE_KEY: note}
    if example is not None:
        options["examples"] = [example]
    if default_factory is not None:
        options["default_factory"] = default_factory
    else:
        options["default"] = default
    return Field(**options, **limits)


# 把字段说明整理成接口文档里的一句中文。
def describe(text: str, unit: str, rule: str, empty: str) -> str:
    parts = [text]
    if unit:
        parts.append(f"单位：{unit}")
    if empty:
        parts.append(f"为空表示：{empty}")
    if rule:
        parts.append(f"规则：{rule}")
    return "；".join(parts)


# 读取一个模型全部字段的说明；没有用 meaning() 声明的字段含义为空。
def notes_of(model: type[BaseModel]) -> dict[str, FieldNote]:
    notes = {}
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        raw = extra.get(NOTE_KEY, {})
        values = raw if isinstance(raw, dict) else {}
        notes[name] = FieldNote(
            name=name,
            meaning=str(values.get("meaning", "")),
            unit=str(values.get("unit", "")),
            rule=str(values.get("rule", "")),
            empty=str(values.get("empty", "")),
            log_value=bool(values.get("log_value", False)),
            secret=bool(values.get("secret", False)),
            has_default=not info.is_required(),
        )
    return notes


# 判断字段类型是否允许空值。
def allows_none(annotation: Any) -> bool:
    if annotation is None or annotation is type(None):
        return True
    if get_origin(annotation) in (Union, types.UnionType):
        return any(allows_none(item) for item in get_args(annotation))
    return False


# 找出字段类型里嵌套的 pydantic 模型，用于逐层检查字段说明。
def nested_models(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for item in get_args(annotation):
        found.extend(nested_models(item))
    return found


# 检查一个模型及其嵌套模型的字段说明是否写全，返回问题清单。
def check_notes(model: type[BaseModel], place: str, seen: set[type] | None = None) -> list[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return []
    seen.add(model)
    problems = []
    notes = notes_of(model)
    for name, info in model.model_fields.items():
        note = notes[name]
        where = f"{place} 的字段 {model.__name__}.{name}"
        if not note.meaning:
            problems.append(f"{where} 没有用 meaning() 写中文含义")
        if allows_none(info.annotation) and not note.empty:
            problems.append(f"{where} 允许为空，但没有用 empty= 说明空值代表什么")
        if note.secret and note.log_value:
            problems.append(f"{where} 同时标记了 secret 和 log_value，敏感字段不能记录取值")
        for inner in nested_models(info.annotation):
            problems.extend(check_notes(inner, place, seen))
    return problems
