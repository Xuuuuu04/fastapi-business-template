from dataclasses import replace
from pathlib import Path

import pytest
from fastapi_check.development_rules import unfinished_steps

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.errors.framework import ConfigError, StepRuleBroken
from shared.flow.flow import Flow
from shared.modules.catalog import Catalog
from shared.records.evidence import run_evidence
from shared.records.stores import RunFilter
from shared.scenarios.simulation import simulate
from tests.framework.test_observation_points import Input, Output, module, operation
from tests.testing_app import make_settings


def skeleton_module():
    return replace(
        module,
        provides={
            operation: Flow(
                "合成模拟骨架",
                work=module.provides[operation].work,
                result="result",
                steps=[replace(part, simulated=True) for part in module.provides[operation].steps],
            )
        },
    )


def calculate(data) -> None:
    data.partial = data.amount * 2


def produce(data) -> None:
    data.result = Output(total=data.partial + 1)


@pytest.mark.anyio
async def test_simulation_requires_explicit_context_and_marks_evidence(tmp_path: Path) -> None:
    built = build(make_settings(tmp_path), modules=[skeleton_module()])
    providers = {(operation.name, "calculate"): calculate, (operation.name, "produce"): produce}
    try:
        with pytest.raises(StepRuleBroken, match="测试提供者"):
            await built.runtime.run(operation, Input(amount=4), caller=SYSTEM)
        with simulate(providers):
            result = await built.runtime.run(operation, Input(amount=4), caller=SYSTEM)
        assert result.total == 9
        records = await built.recorder.store.recent(RunFilter(), 10)
        successful = next(record for record in records if record.status == "ok")
        evidence = run_evidence(successful)
        assert evidence["simulated"] and all(step["simulated"] for step in evidence["steps"])
        built.runtime.allow_simulation = False
        with simulate(providers), pytest.raises(StepRuleBroken, match="test配置"):
            await built.runtime.run(operation, Input(amount=4), caller=SYSTEM)
    finally:
        await built.close()


def test_production_build_rejects_skeleton(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.env = "production"
    with pytest.raises(ConfigError, match="占位步骤"):
        build(settings, modules=[skeleton_module()])


def test_delivery_refuses_mock_implementation() -> None:
    assert any("占位或模拟步骤" in text for text in unfinished_steps(Catalog([skeleton_module()])))


def test_delivery_refuses_placeholder_steps() -> None:
    from dataclasses import replace

    from shared.flow.flow import Flow

    module = skeleton_module()
    item, flow = next(iter(module.provides.items()))

    def rebuilt(**flags: bool) -> Catalog:
        steps = [replace(part, **flags) for part in flow.steps]
        marked = Flow(flow.title, work=flow.work, result=flow.result, steps=steps)
        return Catalog([replace(module, provides={item: marked})])

    assert unfinished_steps(rebuilt(simulated=False, placeholder=False)) == []
    problems = unfinished_steps(rebuilt(simulated=False, placeholder=True))
    assert problems and all("占位或模拟步骤" in text for text in problems)
