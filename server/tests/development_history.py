"""
记录 fastapi_check.check 实际执行的测试及操作状态，供项目开发视图查看。
只在 APP_DEVELOPMENT_RESULT 指定临时输出时启用，直接运行 pytest 不会保存开发历史。
"""

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from shared.records.evidence import run_evidence
from tests.failure_reports import FINISHED

CASES: dict[str, dict[str, Any]] = {}


# 每轮 pytest 从空结果开始，兼容进程内多次执行。
def pytest_sessionstart(session: pytest.Session) -> None:
    CASES.clear()


# 明确标记对应的样例；只保存编号，不读取参数值或业务数据。
def scenario_ids(item: pytest.Item) -> list[str]:
    identities = []
    for marker in item.iter_markers("rule_case"):
        if (
            marker.kwargs
            or len(marker.args) != 1
            or not isinstance(marker.args[0], str)
            or not re.fullmatch(r"[a-z][a-z0-9_]*\.R-\d+-C\d+", marker.args[0])
        ):
            raise pytest.UsageError(f"{item.nodeid}: rule_case 需要一个 module.R-规则-C样例 编号")
        identities.append(marker.args[0])
    return sorted(set(identities))


# 收集时就暴露标记格式错误，不能留到测试结束再悄悄丢弃。
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        scenario_ids(item)


# 全部阶段完成才记为通过；非严格 XPASS 也不能作为规则通过证据。
def case_outcome(phases: dict[str, str]) -> str:
    if "failed" in phases.values():
        return "failed"
    if "skipped" in phases.values():
        return "skipped"
    return "passed" if len(phases) == 3 else "unrecorded"


# 测试完成后保存状态；失败、跳过和预期失败不会被记为通过。
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if not os.environ.get("APP_DEVELOPMENT_RESULT"):
        return
    case = CASES.setdefault(
        item.nodeid,
        {"nodeid": item.nodeid, "runs": [], "scenario_ids": scenario_ids(item), "phases": {}},
    )
    expected_failure = hasattr(report, "wasxfail")
    case["phases"][report.when] = (
        "failed" if report.failed else "skipped" if report.skipped or expected_failure else "passed"
    )
    case.setdefault("durations", {})[report.when] = round(report.duration, 6)
    if expected_failure:
        case["xfail"] = "xpassed" if report.passed else "xfailed"
    case["outcome"] = case_outcome(case["phases"])
    if report.when == "call":
        case["runs"] = [run_evidence(run) for run in FINISHED]


# 所有结束钩子完成后记录最终返回值，包括完整检查的操作覆盖失败。
@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    output = os.environ.get("APP_DEVELOPMENT_RESULT")
    if output:
        Path(output).write_text(
            json.dumps(
                {"exit_code": int(session.exitstatus), "cases": list(CASES.values())},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
