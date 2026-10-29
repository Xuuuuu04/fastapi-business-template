import asyncio
import hashlib
import json
import secrets
import traceback
from dataclasses import asdict
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from pydantic_core import to_jsonable_python

from shared.data.models import Data
from shared.db.budget import DEFAULT_BUDGET, prior_totals
from shared.errors.framework import StepRuleBroken
from shared.errors.kinds import BusinessError
from shared.flow.flow import Flow
from shared.flow.inject import tools_for
from shared.flow.scope import Scope
from shared.flow.step import Condition, Step, source_of
from shared.flow.view import FieldTypes, StepView, missing_writes
from shared.modules.catalog import Binding
from shared.records.models import RunRecord, StepRecord
from shared.records.values import describe_value, shape_text
from shared.scenarios.recording import record_step
from shared.scenarios.simulation import run_simulated
from shared.timing.current import monotonic
from shared.timing.current import now as business_now


async def execute(binding: Binding, input: Data, scope: Scope, run: RunRecord) -> Data:
    item = binding.contract
    if not isinstance(input, item.input):
        raise StepRuleBroken(
            f"调用“{item.title}”需要 {item.input.__name__}，实际传入 {type(input).__name__}"
        )
    run.simulated = any(part.simulated for part in binding.flow.steps)
    values = start_values(binding.flow, input)
    for part in binding.flow.steps:
        await run_part(part, values, scope, run, binding)
    result = values.get(binding.flow.result)
    if not isinstance(result, item.output):
        raise StepRuleBroken(
            f"流程“{binding.flow.title}”没有得到 {item.output.__name__} 类型的结果"
        )
    return result


def start_values(flow: Flow, input: Data) -> dict[str, Any]:
    values = {name: getattr(input, name) for name in type(input).model_fields}
    for name, info in flow.work.model_fields.items():
        if name not in values and not info.is_required():
            values[name] = info.get_default(call_default_factory=True)
    return values


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
        calcs=[f"{func.__name__} · {source_of(func)}" for func in part.calcs],
        database_complete=True,
        database_explain=scope.runtime.query_policy.explain_enabled(),
        query_limits=asdict(binding.contract.query_budget or DEFAULT_BUDGET),
        query_prior=prior_totals(run),
        outputs_recorded=True,
        simulated=part.simulated,
        started_at=business_now(),
    )
    run.steps.append(record)
    tracer = scope.runtime.telemetry
    span = (
        tracer.tracer.start_span("step", attributes={"run.id": run.id, "step.name": part.name})
        if tracer is not None
        else None
    )
    token = otel_context.attach(trace.set_span_in_context(span)) if span else None
    run.updated_at = record.started_at
    started = monotonic()
    try:
        if part.when is not None and not run_condition(part.when, values, binding.types, record):
            record.status = "skipped"
            return
        await run_step(part, values, scope, run, record, binding)
        record_step(part, values, scope, run.contract)
        record.status = "ok"
    except BaseException as error:
        record.status = "failed"
        describe_error(record, error)
        raise
    finally:
        record.elapsed_ms = (monotonic() - started) * 1000
        run.updated_at = business_now()
        if span is not None and token is not None:
            span.set_attribute("step.status", record.status)
            span.set_attribute("step.elapsed_ms", record.elapsed_ms)
            otel_context.detach(token)
            span.end()


def decide(when: Condition, values: dict[str, Any], types: FieldTypes) -> bool:
    view = StepView(values, when.reads, (), types, f"条件“{when.title}”")
    result = when.func(view)
    if not isinstance(result, bool):
        raise StepRuleBroken(f"条件“{when.title}”必须返回 True 或 False")
    return result


def run_condition(
    when: Condition, values: dict[str, Any], types: FieldTypes, record: StepRecord
) -> bool:
    record.condition, record.condition_name, record.condition_source = (
        when.title,
        when.name,
        when.source,
    )
    started = monotonic()
    try:
        record.condition_result = decide(when, values, types)
        return record.condition_result
    finally:
        record.condition_elapsed_ms = (monotonic() - started) * 1000


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
    try:
        if part.simulated:
            returned = await run_simulated(
                part,
                view,
                binding.contract.name,
                allowed=scope.runtime.allow_simulation,
            )
        else:
            async with tools_for(part, scope, run, record, binding.module) as tools:
                if part.is_async:
                    returned = await part.func(view, **tools)
                elif part.heavy:
                    returned = await scope.runtime.heavy.run(part.func, view, **tools)
                else:
                    returned = part.func(view, **tools)
        check_return(returned, part)
        missing = missing_writes(view)
        if missing:
            labels = "、".join(binding.types.label(name) for name in missing)
            raise StepRuleBroken(f"步骤“{part.title}”声明会写入 {labels}，但结束时没有写入")
        if before is not None:
            check_unchanged(part, values, before, binding.types)
    finally:
        record_outputs(part, view, values, binding.types, record)


def check_return(returned: Any, part: Step) -> None:
    if returned is not None:
        close = getattr(returned, "close", None)
        if asyncio.iscoroutine(returned) and callable(close):
            close()
        raise StepRuleBroken(
            f"步骤“{part.title}”返回了值；步骤的结果要写到 data 的字段上，不要 return"
        )


def record_outputs(
    part: Step, view: StepView, values: dict[str, Any], types: FieldTypes, record: StepRecord
) -> None:
    missing = set(missing_writes(view))
    written = [name for name in part.writes if name not in missing]
    record.values = [describe_value(values[name], types.notes[name]) for name in written]
    record.outputs = {
        name: "已写入（敏感字段，不记录内容）"
        if types.notes[name].secret
        else shape_text(values[name])
        for name in written
    }


def fingerprints(values: dict[str, Any], names: tuple[str, ...]) -> dict[str, str]:
    return {name: fingerprint(values[name]) for name in names if name in values}


def fingerprint(value: Any) -> str:
    text = json.dumps(to_jsonable_python(value, fallback=repr), sort_keys=True, default=repr)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def check_unchanged(
    part: Step, values: dict[str, Any], before: dict[str, str], types: FieldTypes
) -> None:
    changed = [name for name, digest in before.items() if fingerprint(values[name]) != digest]
    if changed:
        labels = "、".join(types.label(name) for name in changed)
        raise StepRuleBroken(
            f"步骤“{part.title}”原地修改了只读字段 {labels}；需要修改时请写入新的字段"
        )


def describe_error(record: StepRecord, error: BaseException) -> None:
    if isinstance(error, BusinessError):
        record.error_code, record.error_message = error.code, error.detail
    elif isinstance(error, asyncio.CancelledError):
        record.error_code, record.error_message = (
            "cancelled",
            "执行被取消（客户端断开、超时或服务停止）",
        )
    else:
        record.error_code = type(error).__name__
        record.error_message = type(error).__name__
    record.error_place = error_place(error)


def error_place(error: BaseException) -> str:
    place = ""
    for frame in traceback.extract_tb(error.__traceback__):
        path = frame.filename.replace("\\", "/")
        if "/service/" in path:
            place = "service/" + path.split("/service/", 1)[1] + f":{frame.lineno}"
    return place
