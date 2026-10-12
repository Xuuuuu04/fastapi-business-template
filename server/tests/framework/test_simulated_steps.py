"""
骨架模拟明确注入并保留模拟身份，不能在生产运行或被交付检查视作实际实现。
"""

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


# 标记独立测试步骤，模拟提供者只接收受限StepView，实际业务目录仍为空。
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


# 模拟计算不从确认预期生成，最终断言仍由测试单独书写。
def calculate(data) -> None:
    data.partial = data.amount * 2


# 独立测试提供者按公开数据模型构造返回，正式步骤没有这份提供者。
def produce(data) -> None:
    data.result = Output(total=data.partial + 1)


# 骨架只能在test配置显式提供者范围内执行，记录和压缩历史都保留模拟身份。
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


# 生产组装在打开实际资源之前拒绝模拟实现。
def test_production_build_rejects_skeleton(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.env = "production"
    with pytest.raises(ConfigError, match="模拟骨架"):
        build(settings, modules=[skeleton_module()])


# 默认开发仍能观察骨架，交付才要求全部换成实际实现。
def test_delivery_refuses_mock_implementation(tmp_path: Path, monkeypatch) -> None:
    catalog = Catalog([skeleton_module()])
    monkeypatch.setenv("APP_DEVELOPMENT_DELIVERY", "1")
    assert any(
        p.rule == "simulated_implementation" for p in check_development_rules(catalog, tmp_path)
    )
    monkeypatch.setenv("APP_DEVELOPMENT_DELIVERY", "0")
    assert not check_development_rules(catalog, tmp_path)
