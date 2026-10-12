"""
离线面板颜色验证当前源码、双库整链和稳定性边界，缺证据与旧证据不能染绿。
"""

import copy

from fastapi_project.development.panel_evidence import node_evidence


# 合成两个真实包声明与公开操作，只用于状态计算，不生成正式业务。
def status() -> dict:
    modules = {
        name: {
            "fingerprint": name + "-current",
            "operations": [{"name": name + ".run", "implementation": "real"}],
        }
        for name in ("sample_source", "sample_chain")
    }
    return {
        "modules": modules,
        "tasks": [],
        "dependencies": {"sample_chain": {"sample_source": ["运行"]}},
    }


# 同一轮两个库都真实执行两包操作，数据是独立合成状态而非产品记录。
def check(identity: str) -> dict:
    current = status()
    cases = [
        {
            "nodeid": "tests/modules/" + name + "/test_run.py::test_run",
            "outcome": "passed",
            "runs": [{"operation": name + ".run", "status": "ok"}],
        }
        for name in current["modules"]
    ]
    return {
        "id": identity,
        "finished_at": "2026-10-13T00:00:00+00:00",
        "passed": True,
        "source_changed": False,
        "scope": {"kind": "all"},
        "fingerprints": {
            name: module["fingerprint"] for name, module in current["modules"].items()
        },
        "suites": [
            {"database": database, "exit_code": 0, "cases": copy.deepcopy(cases)}
            for database in ("sqlite", "postgresql")
        ],
    }


# 当前链三个双库成功才稳定；计划、未知、骨架、过期、任务状态单独表达。
def test_panel_states_do_not_invent_completion() -> None:
    current = status()
    assert node_evidence("future_package", current, [])["state"] == "planned"
    assert node_evidence("sample_source", current, [])["state"] == "unknown"
    records = [check(str(number)) for number in range(3)]
    assert node_evidence("sample_source", current, records)["state"] == "stable"
    assert node_evidence("sample_source", current, records[:2])["state"] == "checked"
    current["tasks"] = [{"package": "sample_source", "state": "active"}]
    assert node_evidence("sample_source", current, records)["state"] == "developing"
    current["tasks"] = []
    current["modules"]["sample_source"]["fingerprint"] = "modified-source"
    assert node_evidence("sample_source", current, records)["state"] == "stale"
    current["modules"]["sample_source"]["operations"][0]["implementation"] = "skeleton"
    assert node_evidence("sample_source", current, records)["state"] == "skeleton"


# 双库缺项、缺实际执行、调用方缺覆盖和跳过都不能提供整链稳定证据。
def test_panel_requires_complete_chain_and_real_execution() -> None:
    records = [check(str(number)) for number in range(3)]
    for fault in ("database", "caller", "skip", "simulated", "empty"):
        changed = copy.deepcopy(records)
        last = changed[-1]
        if fault == "database":
            last["suites"].pop()
        elif fault == "caller":
            del last["fingerprints"]["sample_chain"]
        elif fault == "skip":
            last["suites"][0]["cases"][0]["outcome"] = "skipped"
        elif fault == "simulated":
            last["suites"][0]["cases"][0]["runs"][0]["simulated"] = True
        else:
            last["suites"][0]["cases"] = []
        assert node_evidence("sample_source", status(), changed)["state"] == "checked"


# 同源码的成功失败冲突须显示不稳定，随后局部成功也不能隐藏失败。
def test_panel_flaky_and_quick_check_boundaries() -> None:
    failed = check("failed")
    failed["passed"] = False
    records = [failed, check("one"), check("two"), check("three")]
    evidence = node_evidence("sample_source", status(), records)
    assert evidence["flaky"] and evidence["state"] == "checked"
    quick = check("quick")
    quick["scope"] = {"kind": "quick"}
    evidence = node_evidence("sample_source", status(), [failed, quick])
    assert evidence["state"] == "failed"
