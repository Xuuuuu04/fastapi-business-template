"""
骨架测试读取独立样例；模拟只填测试提供者，实际实现仍用同一组输入与中间观察验证。
"""

import json
from pathlib import Path
from typing import Any

from app.setup.build import Services
from shared.access.caller import SYSTEM
from shared.scenarios.observations import (
    ExpectedObservation,
    ObservationJournal,
    ObservationPoint,
    capture,
)
from shared.scenarios.simulation import simulate


# 只从当前产品的样例目录读取，不读取模板本机原话或运行数据库。
def fixture(project: Path, identity: str) -> dict[str, Any]:
    module = identity.split(".")[0]
    found = [
        json.loads(path.read_text()) for path in (project / "doc" / module / "cases").glob("*.json")
    ]
    selected = [item for item in found if item.get("id") == identity]
    assert len(selected) == 1, "独立样例缺失或重复"
    case = selected[0]
    assert not case["initial"] and not case.get("database") and not case.get("effects"), (
        "此短骨架不猜数据库初始化或外部效果断言，请编写独立的真实状态测试"
    )
    return case


# 按已声明类型构造测试提供者，提供者从不进入正式业务文件。
def provider(binding, case: dict[str, Any]):
    # 原始入参也核对，不能让固定mock产出掩盖跨包参数连接错误。
    def fill(data) -> None:
        actual = {name: getattr(data, name) for name in binding.contract.input.model_fields}
        assert actual == case["input"], "模拟步骤收到了与独立样例不同的输入"
        data.result = binding.contract.output(**case["expected"])

    return fill


# 顺着规格引用准备有限测试提供者，真实实现不读取它们。
async def run_case(
    services: Services, project: Path, operation: str, identity: str, dependencies: dict[str, str]
) -> tuple[dict, dict]:
    data = fixture(project, identity)
    cases = {
        operation: data,
        **{name: fixture(project, case) for name, case in dependencies.items()},
    }
    providers, expected = {}, []
    for name, case in cases.items():
        binding = services.runtime.catalog.by_name[name]
        if len(binding.flow.steps) == 1:
            providers[(name, "build_result")] = provider(binding, case)
            expected += [
                ExpectedObservation(ObservationPoint(name, "build_result", field), value)
                for field, value in case["input"].items()
            ]
        expected.append(
            ExpectedObservation(ObservationPoint(name, "build_result", "result"), case["expected"])
        )
    for case in cases.values():
        for observation in case.get("observations", []):
            assert set(observation) == {"point", "value"}, "观察预期需要独立point与value"
            expected.append(
                ExpectedObservation(ObservationPoint(**observation["point"]), observation["value"])
            )
    journal = ObservationJournal()
    binding = services.runtime.catalog.by_name[operation]
    with simulate(providers), capture(journal):
        result = await services.runtime.run(
            binding.contract, binding.contract.input(**data["input"]), caller=SYSTEM
        )
    differences = journal.compare(expected)
    assert not differences, f"最早不一致或未知位置：{differences[0].point if differences else None}"
    return result.model_dump(mode="json"), data["expected"]
