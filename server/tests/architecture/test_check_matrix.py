import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.cache import cached_round, execution_profile
from fastapi_check.matrix import CheckOptions, databases, execute_matrix
from fastapi_project.development.history import save_check


def test_parallel_budget_and_distinct_resources() -> None:
    recorded = []

    def run(title, arguments, environment, database):
        recorded.append((arguments, environment, database))
        return True, {"database": database, "exit_code": 0, "cases": []}

    outcomes = execute_matrix(
        ("sqlite", "postgresql"),
        "postgresql://test.invalid/control",
        ["-m", "pytest"],
        {},
        CheckOptions(workers=4),
        run,
    )
    assert [result[0] for result in outcomes] == ["sqlite", "postgresql"]
    budgets = {database: int(arguments[-1]) for arguments, _, database in recorded}
    assert budgets == {"sqlite": 2, "postgresql": 2} and sum(budgets.values()) == 4
    assert all("--dist=load" in arguments for arguments, _, _ in recorded)
    assert all("--maxschedchunk=2" in arguments for arguments, _, _ in recorded)
    assert {value[0]: value[2]["workers"] for value in outcomes} == budgets
    assert all(value[2]["total_worker_budget"] == 4 for value in outcomes)
    assert len({env["APP_TEST_RUN_ID"] for _, env, _ in recorded}) == 2
    assert "APP_TEST_CONTROL_URL" not in next(env for _, env, db in recorded if db == "sqlite")


def test_profile_is_private_and_changes_with_services(monkeypatch) -> None:
    first = execution_profile(CheckOptions(), "postgresql://user:secret-a@test.invalid/control")
    second = execution_profile(CheckOptions(), "postgresql://user:secret-b@test.invalid/control")
    assert first != second and "secret-a" not in json.dumps(first)


def test_cache_preserves_failure_and_version(tmp_path: Path) -> None:
    value = {
        "fingerprints": {},
        "system_fingerprint": "s1",
        "source_changed": False,
        "scope": {"kind": "all"},
        "execution_profile": {},
        "passed": True,
        "checks": {"默认测试": True},
        "suites": [],
    }
    save_check(tmp_path, value)
    assert cached_round(tmp_path, {}, "s1", {"kind": "all"}, {})
    assert not cached_round(tmp_path, {}, "s2", {"kind": "all"}, {})
    save_check(tmp_path, {**value, "passed": False})
    assert not cached_round(tmp_path, {}, "s1", {"kind": "all"}, {})


def test_parallel_results_are_combined(tmp_path: Path) -> None:
    tests = tmp_path / "test_items.py"
    tests.write_text(
        'import pytest\n@pytest.mark.parametrize("n",range(12))\n'
        "def test_value(n):\n    assert n >= 0\n"
    )
    target = tmp_path / "result.json"
    environment = {key: value for key, value in os.environ.items() if not key.startswith("APP_")}
    environment["APP_DEVELOPMENT_RESULT"] = str(target)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--dist=worksteal",
            "-n",
            "2",
            "--confcutdir",
            str(tmp_path),
            "-p",
            "tests.development_history",
            str(tests),
        ],
        env=environment,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(target.read_text())
    assert len(data["cases"]) == 12 and data["exit_code"] == 0


def test_database_selection_requires_target() -> None:
    with pytest.raises(ValueError):
        databases("", "both")
    assert databases("", "sqlite") == ("sqlite",)
