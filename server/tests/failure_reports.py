import json
import secrets
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from shared.flow.runtime import Runtime
from shared.graphs.observed import run_report
from shared.records.evidence import run_evidence
from shared.records.models import RunRecord

FINISHED: list[RunRecord] = []
MAX_REPORTS = 3
FAILED = ("failed", "refused")
FAILURE_FILE = pytest.StashKey[Path]()


@pytest.fixture(autouse=True, scope="session")
def keep_finished_runs() -> Iterator[None]:
    original = Runtime.close_run

    async def kept(self: Runtime, run: RunRecord, status: str) -> None:
        await original(self, run, status)
        FINISHED.append(run)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Runtime, "close_run", kept)
        yield


@pytest.fixture(autouse=True)
def clear_finished_runs() -> None:
    FINISHED.clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    for title, text in failure_reports(FINISHED):
        report.sections.append((title, text))
    folder = Path(__file__).resolve().parents[1] / "var/development/failures"
    path = save_finished_runs(folder, item.nodeid, FINISHED)
    item.stash[FAILURE_FILE] = path
    report.sections.append(("完整运行记录", f"{path}（测试环境清理前补入流程和任务状态）"))


def failure_reports(runs: list[RunRecord]) -> list[tuple[str, str]]:
    roots = [run for run in runs if not run.parent_id and run.status in FAILED]
    reports = []
    for root in roots[-MAX_REPORTS:]:
        tree = sorted((run for run in runs if run.root_id == root.id), key=started)
        reports.append((f"运行报告 {root.id}（{root.title}）", run_report(tree, root.id)))
    return reports


def started(run: RunRecord) -> float:
    return run.started_at


def save_finished_runs(folder: Path, nodeid: str, runs: list[RunRecord]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{secrets.token_hex(12)}.json"
    safe = [replace(run, caller="未保存", request_id="", segment_cursor={}) for run in runs]
    roots = [run for run in safe if not run.parent_id]
    reports = []
    for root in roots:
        tree = sorted((run for run in safe if run.root_id == root.id), key=started)
        reports.append(dict(id=root.id, text=run_report(tree, root.id)))
    path.write_text(
        json.dumps(
            dict(nodeid=nodeid, runs=[run_evidence(run) for run in runs], reports=reports),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
