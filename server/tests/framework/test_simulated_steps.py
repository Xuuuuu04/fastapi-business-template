from dataclasses import replace
from pathlib import Path

import pytest
from fastapi_check.quality.docs import check_development_rules
from fastapi_project.development.check_assets import compact_case

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
        case = compact_case({"nodeid": "synthetic", "runs": [evidence]}, tmp_path)
        assert case["runs"][0]["simulated"]
        built.runtime.allow_simulation = False
        with simulate(providers), pytest.raises(StepRuleBroken, match="test配置"):
            await built.runtime.run(operation, Input(amount=4), caller=SYSTEM)
    finally:
        await built.close()


def test_production_build_rejects_skeleton(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.env = "production"
    with pytest.raises(ConfigError, match="模拟骨架"):
        build(settings, modules=[skeleton_module()])


def test_delivery_refuses_mock_implementation(tmp_path: Path, monkeypatch) -> None:
    catalog = Catalog([skeleton_module()])
    monkeypatch.setenv("APP_DEVELOPMENT_DELIVERY", "1")
    assert any(
        p.rule == "simulated_implementation" for p in check_development_rules(catalog, tmp_path)
    )
    monkeypatch.setenv("APP_DEVELOPMENT_DELIVERY", "0")
    assert not check_development_rules(catalog, tmp_path)
