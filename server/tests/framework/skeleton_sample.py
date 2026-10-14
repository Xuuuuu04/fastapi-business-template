"""
三个包的合成规格与独立预期，只供模板生成验收，不登记到空模板或产品数据库。
"""

import json
from pathlib import Path


# 相同标量字段用于检查真实跨包传递，样例数值不进入正式骨架源码。
def specification() -> dict:
    field = {"value": {"type": "int", "meaning": "合成数量"}}
    operations = [
        ("sample_sources", "load", 496116, 992232),
        ("sample_counts", "advance", 992232, 992233),
        ("sample_chain", "run", 496116, 992233),
    ]
    packages = []
    for package, action, _, _ in operations:
        operation = {
            "name": action,
            "title": "合成计算",
            "access": "public",
            "effect": "query",
            "input": field,
            "output": field,
            "cases": [f"{package}.R-01-C01"],
        }
        if package == "sample_chain":
            operation.update(
                calls=[
                    {
                        "operation": "sample_sources.load",
                        "input": {"value": "input.value"},
                        "case": "sample_sources.R-01-C01",
                    },
                    {
                        "operation": "sample_counts.advance",
                        "input": {"value": "sample_sources.load.value"},
                        "case": "sample_counts.R-01-C01",
                    },
                ],
                returns={"value": "sample_counts.advance.value"},
            )
        packages.append(
            {
                "name": package,
                "title": "合成样例包",
                "kind": "workflow" if package == "sample_chain" else "capability",
                "operations": [operation],
            }
        )
    return json.loads(json.dumps({"line": "合成计算链", "packages": packages}))


# 独立资料先写，生成器不能通过实际实现来算这些值或改它们。
def write_inputs(project: Path) -> Path:
    for package, action, input, expected in (
        ("sample_sources", "load", 496116, 992232),
        ("sample_counts", "advance", 992232, 992233),
        ("sample_chain", "run", 496116, 992233),
    ):
        folder = project / "doc" / package
        (folder / "cases").mkdir(parents=True, exist_ok=True)
        case_path = next((folder / "cases").glob("*.json"), folder / "cases/one.json")
        case = {
            "id": f"{package}.R-01-C01",
            "input": {"value": input},
            "initial": {},
            "expected": {"value": expected},
            "assertions": ["数量符合独立预期"],
            "tests": [f"tests/modules/{package}/test_{action}.py::test_case"],
        }
        if package == "sample_chain":
            # 观察点按被调用的操作命名：步骤 fetch_包_操作，字段 包_操作。
            point = {
                "operation": "sample_chain.run",
                "step": "fetch_sample_counts_advance",
                "field": "sample_counts_advance",
            }
            case["observations"] = [{"point": point, "value": {"value": expected}}]
        case_path.write_text(json.dumps(case))
        (folder / "rules.md").write_text(
            "# 合成规则\n\n### R-01 合成计算\n\n独立合成样例，不是人类业务验收。\n\n"
            "| 样例编号 | 输入 | 结果 |\n| --- | --- | --- |\n"
            f"| R-01-C01 | {input} | {expected} |\n"
        )
    spec = project / "skeleton-spec.json"
    spec.write_text(json.dumps(specification(), ensure_ascii=False, indent=2))
    return spec


# 实际计算来自算法，不从expected常量生成；wrong供中间步骤定位反例使用。
def implement(project: Path, *, wrong: bool = False, only: str = "") -> None:
    for package, action, kind, expression in (
        ("sample_sources", "load", "Load", "data.value * 2" + (" - 1" if wrong else "")),
        ("sample_counts", "advance", "Advance", "data.value + 1"),
    ):
        if only and package != only:
            continue
        path = project / "server/service" / package / "steps" / ("build_" + action + ".py")
        path.write_text(
            '"""\n合成实际计算，不读取样例预期。\n"""\n\n'
            f"from service.{package}.data_{action} import {kind}Work, {kind}Output\n"
            "from shared.public import step\n\n\n"
            "# 按独立合成算法计算数量。\n"
            "@step('计算数量', reads=['value'], writes=['result'], "
            "observes=['value', 'result'], simulated=False)\n"
            f"def build_result(data: {kind}Work) -> None:\n"
            f"    data.result = {kind}Output(value={expression})\n"
        )
