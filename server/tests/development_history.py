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
WORKER_RESULTS: list[dict[str, Any]] = []


def pytest_sessionstart(session: pytest.Session) -> None:
    CASES.clear()
    WORKER_RESULTS.clear()


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


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        scenario_ids(item)


def case_outcome(phases: dict[str, str]) -> str:
    if "failed" in phases.values():
        return "failed"
    if "skipped" in phases.values():
        return "skipped"
    return "passed" if len(phases) == 3 else "unrecorded"


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


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    output = os.environ.get("APP_DEVELOPMENT_RESULT")
    if output:
        path = Path(output)
        cases = list(CASES.values())
        worker = getattr(session.config, "workerinput", {}).get("workerid")
        if worker:
            path = path.with_name(path.stem + "-" + worker + path.suffix)
            session.config.workeroutput["development_result"] = str(path)
        elif WORKER_RESULTS:
            cases = [case for result in WORKER_RESULTS for case in result["cases"]]
        path.write_text(
            json.dumps(
                {
                    "exit_code": int(session.exitstatus),
                    "cases": cases,
                    "database": "postgresql"
                    if os.environ.get("APP_TEST_CONTROL_URL")
                    or os.environ.get("APP_TEST_DATABASE_URL", "").startswith("postgresql")
                    else "sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: Any) -> None:
    output = node.workeroutput.get("development_result")
    if output:
        WORKER_RESULTS.append(json.loads(Path(output).read_text()))
