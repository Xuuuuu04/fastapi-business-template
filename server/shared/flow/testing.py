import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from shared.access.caller import DEVELOPER, Caller
from shared.data.models import Data, WorkData
from shared.errors.framework import StepRuleBroken
from shared.flow.inject import NoteWriter
from shared.flow.step import Step
from shared.flow.view import FieldTypes, StepView, missing_writes
from shared.model_calls.gate import ModelGate
from shared.model_calls.service import ModelService
from shared.modules.contract import Contract
from shared.records.models import StepRecord
from shared.scenarios.observations import (
    ExpectedObservation,
    ObservationJournal,
    ObservationPoint,
    capture,
)
from shared.scenarios.simulation import simulate
from shared.timing.clock import FakeClock

Fake = Callable[[Any], Awaitable[Data]]


@dataclass
class StepResult:
    values: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    later: list[tuple[str, Data]] = field(default_factory=list)


def try_step(part: Step, work: type[WorkData], **values: Any) -> StepResult:
    if part.is_async:
        raise StepRuleBroken("async 步骤请使用 try_step_async")
    view, record = prepare(part, work, values)
    tools: dict[str, Any] = {"note": NoteWriter(record)} if "note" in part.params else {}
    if "caller" in part.params:
        tools["caller"] = DEVELOPER
    part.func(view, **tools)
    return finish(part, view, values, record, [])


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
    chosen = {name: tools[name] for name in part.params[1:] if name in tools}
    returned = part.func(view, **chosen)
    if part.is_async:
        await returned
    return finish(part, view, values, record, submitted)


def prepare(
    part: Step, work: type[WorkData], values: dict[str, Any]
) -> tuple[StepView, StepRecord]:
    types = FieldTypes(work)
    view = StepView(values, part.reads, part.writes, types, part.title)
    record = StepRecord(secrets.token_hex(4), part.name, part.title, part.kind, part.source)
    return view, record


def finish(
    part: Step,
    view: StepView,
    values: dict[str, Any],
    record: StepRecord,
    submitted: list[tuple[str, Data]],
) -> StepResult:
    missing = missing_writes(view)
    if missing:
        raise StepRuleBroken(f"步骤“{part.title}”声明会写入 {missing}，但没有写入")
    written = {name: values[name] for name in part.writes}
    return StepResult(written, list(record.notes), submitted)


def fake_call(part: Step, calls: dict[Contract[Any, Any], Fake]) -> Callable[..., Awaitable[Data]]:
    async def call(item: Contract[Any, Any], input: Data) -> Data:
        if item not in part.uses:
            raise StepRuleBroken(f"步骤“{part.title}”调用了未声明的操作 {item.name}")
        if item not in calls:
            raise StepRuleBroken(f"测试没有为 {item.name} 提供替身")
        return await calls[item](input)

    return call


def fake_later(part: Step, submitted: list[tuple[str, Data]]) -> Callable[..., Awaitable[str]]:
    async def later(item: Contract[Any, Any], input: Data, *, key: str = "") -> str:
        if item not in part.later:
            raise StepRuleBroken(f"步骤“{part.title}”登记了未声明的任务 {item.name}")
        submitted.append((item.name, input))
        return f"test-{len(submitted)}"

    return later


__all__ = [
    "ExpectedObservation",
    "FakeClock",
    "ObservationJournal",
    "ObservationPoint",
    "StepResult",
    "capture",
    "simulate",
    "try_step",
    "try_step_async",
]
