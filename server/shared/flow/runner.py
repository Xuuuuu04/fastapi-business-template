"""
按流程声明逐个执行步骤，并记录每一步的状态、耗时、写入字段摘要和错误位置。
步骤只能通过 StepView 读写声明的字段；步骤不能返回值，结果写到 data 的字段上。
开启额外检查时，还会发现步骤原地修改了只读字段的内容。
"""

import asyncio
import hashlib
import json
import secrets
import time
import traceback
from typing import Any

from pydantic_core import to_jsonable_python

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.errors.kinds import BusinessError
from shared.flow.flow import Flow
from shared.flow.inject import tools_for
from shared.flow.scope import Scope
from shared.flow.step import Condition, Step
from shared.flow.view import FieldTypes, StepView, missing_writes
from shared.modules.catalog import Binding
from shared.records.models import RunRecord, StepRecord
from shared.records.values import describe_value


# 执行一个操作的流程并返回结果。
async def execute(binding: Binding, input: Data, scope: Scope, run: RunRecord) -> Data:
    item = binding.contract
    if not isinstance(input, item.input):
        raise StepRuleBroken(
            f"调用「{item.title}」需要 {item.input.__name__}，实际传入 {type(input).__name__}"
        )
    values = start_values(binding.flow, input)
    for part in binding.flow.steps:
        await run_part(part, values, scope, run, binding)
    result = values.get(binding.flow.result)
    if not isinstance(result, item.output):
        raise StepRuleBroken(
            f"流程「{binding.flow.title}」没有得到 {item.output.__name__} 类型的结果"
        )
    return result


# 用操作输入和字段默认值准备流程数据。
def start_values(flow: Flow, input: Data) -> dict[str, Any]:
    values = {name: getattr(input, name) for name in type(input).model_fields}
    for name, info in flow.work.model_fields.items():
        if name not in values and not info.is_required():
            values[name] = info.get_default(call_default_factory=True)
    return values


# 执行流程中的一项：先判断条件，再执行步骤，并记录结果。
async def run_part(
    part: Step, values: dict[str, Any], scope: Scope, run: RunRecord, binding: Binding
) -> None:
    record = StepRecord(
        id=secrets.token_hex(8),
        name=part.name,
        title=part.title,
        kind=part.kind,
        rule=part.rule,
        source=part.source,
        reads=list(part.reads),
        writes=list(part.writes),
        started_at=time.time(),
    )
    run.steps.append(record)
    run.updated_at = record.started_at
    started = time.perf_counter()
    try:
        if part.when is not None:
            record.condition = part.when.title
            if not decide(part.when, values, binding.types):
                record.status = "skipped"
                return
        await run_step(part, values, scope, run, record, binding)
        record.status = "ok"
    except BaseException as error:
        record.status = "failed"
        describe_error(record, error)
        raise
    finally:
        record.elapsed_ms = (time.perf_counter() - started) * 1000
        run.updated_at = time.time()


# 计算条件的结果；条件只能读取声明的字段，必须返回 True 或 False。
def decide(when: Condition, values: dict[str, Any], types: FieldTypes) -> bool:
    view = StepView(values, when.reads, (), types, f"条件「{when.title}」")
    result = when.func(view)
    if not isinstance(result, bool):
        raise StepRuleBroken(f"条件「{when.title}」必须返回 True 或 False")
    return result


# 执行一个步骤并检查它是否按声明写入。
async def run_step(
    part: Step,
    values: dict[str, Any],
    scope: Scope,
    run: RunRecord,
    record: StepRecord,
    binding: Binding,
) -> None:
    view = StepView(values, part.reads, part.writes, binding.types, part.title)
    before = fingerprints(values, part.reads) if scope.runtime.step_checks else None
    async with tools_for(part, scope, run, record, binding.module.store) as tools:
        if part.is_async:
            returned = await part.func(view, **tools)
        elif part.heavy:
            returned = await asyncio.to_thread(part.func, view, **tools)
        else:
            returned = part.func(view, **tools)
    if returned is not None:
        close = getattr(returned, "close", None)
        if asyncio.iscoroutine(returned) and callable(close):
            close()
        raise StepRuleBroken(
            f"步骤「{part.title}」返回了值；步骤的结果要写到 data 的字段上，不要 return"
        )
    missing = missing_writes(view)
    if missing:
        labels = "、".join(binding.types.label(name) for name in missing)
        raise StepRuleBroken(f"步骤「{part.title}」声明会写入 {labels}，但结束时没有写入")
    if before is not None:
        check_unchanged(part, values, before, binding.types)
    record.values = [
        describe_value(values.get(name), binding.types.notes[name]) for name in part.writes
    ]


# 计算只读字段内容的摘要，用于发现原地修改。
def fingerprints(values: dict[str, Any], names: tuple[str, ...]) -> dict[str, str]:
    return {name: fingerprint(values[name]) for name in names if name in values}


# 计算一个值的内容摘要。
def fingerprint(value: Any) -> str:
    text = json.dumps(to_jsonable_python(value, fallback=repr), sort_keys=True, default=repr)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# 检查步骤没有原地修改只读字段，例如对读取的列表 append。
def check_unchanged(
    part: Step, values: dict[str, Any], before: dict[str, str], types: FieldTypes
) -> None:
    changed = [name for name, digest in before.items() if fingerprint(values[name]) != digest]
    if changed:
        labels = "、".join(types.label(name) for name in changed)
        raise StepRuleBroken(
            f"步骤「{part.title}」原地修改了只读字段 {labels}；需要修改时请写入新的字段"
        )


# 把异常整理成步骤记录中的错误码、说明和出错位置。
def describe_error(record: StepRecord, error: BaseException) -> None:
    if isinstance(error, BusinessError):
        record.error_code, record.error_message = error.code, error.detail
    elif isinstance(error, asyncio.CancelledError):
        record.error_code, record.error_message = (
            "cancelled",
            "执行被取消（客户端断开、超时或服务停止）",
        )
    else:
        first = (str(error).splitlines() or [""])[0]
        record.error_code = type(error).__name__
        record.error_message = f"{type(error).__name__}：{first}"[:300]
    record.error_place = error_place(error)


# 找出异常在业务代码中发生的位置，写成“service/模块/文件.py:行号”。
def error_place(error: BaseException) -> str:
    place = ""
    for frame in traceback.extract_tb(error.__traceback__):
        path = frame.filename.replace("\\", "/")
        if "/service/" in path:
            place = "service/" + path.split("/service/", 1)[1] + f":{frame.lineno}"
    return place
