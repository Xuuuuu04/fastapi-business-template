"""
测试失败时附上运行报告：记下每个测试期间结束的运行，测试失败时把其中失败运行的中文排查报告
（停在哪一步、为什么、出错位置、每一步写了什么）加到 pytest 的失败输出里，不必再按运行编号去查。
由 conftest.py 通过 pytest_plugins 加载。
"""

from collections.abc import Iterator
from typing import Any

import pytest

from shared.flow.runtime import Runtime
from shared.graphs.observed import run_report
from shared.records.models import RunRecord

FINISHED: list[RunRecord] = []
MAX_REPORTS = 3
FAILED = ("failed", "refused")


# 在运行结束时记下运行记录，供测试失败时生成报告。
@pytest.fixture(autouse=True, scope="session")
def keep_finished_runs() -> Iterator[None]:
    original = Runtime.close_run

    # 先按原逻辑结束运行，再记下这条运行记录。
    async def kept(self: Runtime, run: RunRecord, status: str) -> None:
        await original(self, run, status)
        FINISHED.append(run)

    Runtime.close_run = kept  # type: ignore[method-assign]
    yield
    Runtime.close_run = original  # type: ignore[method-assign]


# 每个测试开始前清空上一个测试留下的记录。
@pytest.fixture(autouse=True)
def clear_finished_runs() -> None:
    FINISHED.clear()


# 测试执行阶段失败时，把本测试中失败运行的报告加到失败输出。
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    for title, text in failure_reports(FINISHED):
        report.sections.append((title, text))


# 找出失败的最外层运行，每个生成一份包含下层调用的报告，最多三份。
def failure_reports(runs: list[RunRecord]) -> list[tuple[str, str]]:
    roots = [run for run in runs if not run.parent_id and run.status in FAILED]
    reports = []
    for root in roots[-MAX_REPORTS:]:
        tree = sorted((run for run in runs if run.root_id == root.id), key=started)
        reports.append((f"运行报告 {root.id}（{root.title}）", run_report(tree, root.id)))
    return reports


# 按开始时间排列，报告中最外层运行在前。
def started(run: RunRecord) -> float:
    return run.started_at
