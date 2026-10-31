from dataclasses import replace
from typing import Any

import pytest

from shared.errors.framework import StepRuleBroken
from shared.flow.flow import Flow
from shared.flow.step import step
from shared.model_calls.gate import ModelGate
from shared.model_calls.providers import FakeModel
from shared.model_calls.service import ModelService
from shared.modules.call_order import check_call_order
from tests.framework.sample_modules import (
    CalcWork,
    ask_text,
    calc,
    calc_flow,
    describe,
    explain,
    explain_flow,
)


@step("调用保存", uses=[calc])
async def call_save(data: Any, call: Any) -> None: ...


@step("调用模型", uses=[explain])
async def call_model(data: Any, call: Any) -> None: ...


@pytest.mark.parametrize("depth", [1, 2, 4])
@pytest.mark.parametrize("external", [call_model, ask_text])
def test_transitive_writes_before_external_are_rejected(depth: int, external: Any) -> None:
    flows = {calc: calc_flow, explain: explain_flow}
    previous = calc
    for index in range(depth):
        wrapper = replace(calc, name=f"sample_calc.wrapper_{index}")
        part = replace(call_save, uses=(previous,))
        flows[wrapper] = Flow("调用保存", work=CalcWork, result="result", steps=[part])
        previous = wrapper
    root = replace(calc, name="sample_calc.root")
    flows[root] = Flow(
        "先保存后调用",
        work=CalcWork,
        result="result",
        steps=[replace(call_save, uses=(previous,)), external],
    )
    errors = check_call_order(flows)
    assert len(errors) == 1
    assert root.name in errors[0] and "调用保存" in errors[0]


def test_model_before_nested_write_is_allowed() -> None:
    root = replace(calc, name="sample_calc.root")
    flow = Flow("先模型后保存", work=CalcWork, result="result", steps=[call_model, call_save])
    assert check_call_order({root: flow, calc: calc_flow, explain: explain_flow}) == []


@pytest.mark.anyio
async def test_gate_reads_current_transaction_state() -> None:
    started = False
    service = ModelService(FakeModel(), concurrency=1, keep_text=False)
    records = []
    gate = ModelGate(service, (describe,), records, "说明步骤", lambda: started)
    await gate.ask(describe, mark="允许调用")
    started = True
    with pytest.raises(StepRuleBroken, match="说明步骤.*写入事务开始后"):
        await gate.ask(describe, mark="不能调用")
    assert len(records) == 1
