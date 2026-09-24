"""
单独运行一个步骤的测试工具，供 tests/modules 中的业务测试使用。
同样检查读写声明和字段类型；store、其他模块的调用和大模型都由测试传入替身。
"""

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from shared.access.caller import DEVELOPER, Caller
from shared.data.models import Data, WorkData
from shared.errors.framework import StepRuleBroken
from shared.events.event import Event
from shared.flow.inject import NoteWriter
from shared.flow.step import Step
from shared.flow.view import FieldTypes, StepView, missing_writes
from shared.model_calls.gate import ModelGate
from shared.model_calls.service import ModelService
from shared.modules.contract import Contract
from shared.records.models import StepRecord

Fake = Callable[[Any], Awaitable[Data]]


@dataclass
class StepResult:
    values: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    later: list[tuple[str, Data]] = field(default_factory=list)


# 运行一个普通函数写的步骤，返回它写入的字段和数据说明。
def try_step(part: Step, work: type[WorkData], **values: Any) -> StepResult:
    if part.is_async:
        raise StepRuleBroken("async 步骤请使用 try_step_async")
    view, record = prepare(part, work, values)
    tools: dict[str, Any] = {"note": NoteWriter(record)} if "note" in part.params else {}
    if "caller" in part.params:
        tools["caller"] = DEVELOPER
    part.func(view, **tools)
    return finish(part, view, values, record, [])


# 运行任意步骤；calls 按操作给出替身函数，store、model 直接传入替身。
async def try_step_async(
    part: Step,
    work: type[WorkData],
    values: dict[str, Any],
    *,
    store: object = None,
    calls: dict[Contract[Any, Any], Fake] | None = None,
    model: ModelService | None = None,
    caller: Caller = DEVELOPER,
) -> StepResult:
    view, record = prepare(part, work, values)
    submitted: list[tuple[str, Data]] = []
    tools: dict[str, Any] = {"store": store, "caller": caller, "note": NoteWriter(record)}
    tools["call"] = fake_call(part, calls or {})
    tools["model"] = ModelGate(model, part.prompts, record.models, part.title)
    tools["later"] = fake_later(part, submitted)
    tools["publish"] = fake_publish(part, submitted)
    chosen = {name: tools[name] for name in part.params[1:] if name in tools}
    returned = part.func(view, **chosen)
    if part.is_async:
        await returned
    return finish(part, view, values, record, submitted)


# 准备步骤视图和步骤记录。
def prepare(
    part: Step, work: type[WorkData], values: dict[str, Any]
) -> tuple[StepView, StepRecord]:
    types = FieldTypes(work)
    view = StepView(values, part.reads, part.writes, types, part.title)
    record = StepRecord(
        secrets.token_hex(4), part.name, part.title, part.kind, part.rule, part.source
    )
    return view, record


# 检查声明的字段都已写入，并整理结果。
def finish(
    part: Step,
    view: StepView,
    values: dict[str, Any],
    record: StepRecord,
    submitted: list[tuple[str, Data]],
) -> StepResult:
    missing = missing_writes(view)
    if missing:
        raise StepRuleBroken(f"步骤「{part.title}」声明会写入 {missing}，但没有写入")
    written = {name: values[name] for name in part.writes}
    return StepResult(written, list(record.notes), submitted)


# 生成模块调用的替身：只允许调用步骤声明过的操作。
def fake_call(part: Step, calls: dict[Contract[Any, Any], Fake]) -> Callable[..., Awaitable[Data]]:
    # 按操作找到测试给出的替身函数并调用。
    async def call(item: Contract[Any, Any], input: Data) -> Data:
        if item not in part.uses:
            raise StepRuleBroken(f"步骤「{part.title}」调用了未声明的操作 {item.name}")
        if item not in calls:
            raise StepRuleBroken(f"测试没有为 {item.name} 提供替身")
        return await calls[item](input)

    return call


# 生成任务登记的替身：记录登记了哪些任务。
def fake_later(part: Step, submitted: list[tuple[str, Data]]) -> Callable[..., Awaitable[str]]:
    # 记下登记的任务并返回一个假编号。
    async def later(item: Contract[Any, Any], input: Data, *, key: str = "") -> str:
        if item not in part.later:
            raise StepRuleBroken(f"步骤「{part.title}」登记了未声明的任务 {item.name}")
        submitted.append((item.name, input))
        return f"test-{len(submitted)}"

    return later


# 生成事件发布的替身：发布的事件和任务登记记在一起，名称写成“事件:事件名”。
def fake_publish(
    part: Step, submitted: list[tuple[str, Data]]
) -> Callable[..., Awaitable[list[str]]]:
    # 记下发布的事件，不登记订阅方任务。
    async def publish(item: Event, data: Data) -> list[str]:
        if item not in part.publishes:
            raise StepRuleBroken(f"步骤「{part.title}」发布了未声明的事件 {item.name}")
        submitted.append((f"事件:{item.name}", data))
        return []

    return publish
