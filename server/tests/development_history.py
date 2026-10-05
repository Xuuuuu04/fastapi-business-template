"""
记录 tools.check 实际执行的测试及操作状态，供项目开发视图查看。
只在 APP_DEVELOPMENT_RESULT 指定临时输出时启用，直接运行 pytest 不会保存开发历史。
"""

import json
import os
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


# 测试完成后保存状态；失败和跳过不会被记为通过。
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if not os.environ.get("APP_DEVELOPMENT_RESULT"):
        return
    case = CASES.setdefault(item.nodeid, {"nodeid": item.nodeid, "outcome": "passed", "runs": []})
    if report.failed or report.skipped:
        case["outcome"] = "failed" if report.failed else "skipped"
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
