import json
from pathlib import Path
from typing import Any

import pytest
from fastapi_check import check
from fastapi_project.development.selection import Selection
from fastapi_project.development.status import test_status as package_test_status


@pytest.fixture
def recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    evidence: dict[str, Any] = {"runs": [], "records": []}
    monkeypatch.setattr(check, "PROJECT", tmp_path)
    monkeypatch.setattr(check, "module_files", lambda names: ["sample.py"])
    monkeypatch.setattr(
        check, "fingerprints", lambda project, modules, links: dict.fromkeys(modules, "v1")
    )
    monkeypatch.setattr(check, "system_fingerprint", lambda project: "system1")

    def save(project: Path, record: dict[str, Any]) -> Path:
        evidence["records"].append(record)
        return project / "record.json"

    def run(title: str, command: list[str], env: dict[str, str]) -> bool:
        evidence["runs"].append((title, command, dict(env)))
        return True

    def tests(
        title: str, command: list[str], env: dict[str, str], database: str
    ) -> tuple[bool, dict[str, object]]:
        run(title, command, env)
        return True, {"database": database, "exit_code": 0, "cases": []}

    monkeypatch.setattr(check, "save_check", save)
    monkeypatch.setattr(check, "run", run)
    monkeypatch.setattr(check, "run_tests", tests)
    return evidence


def test_multi_module_execution_and_database_evidence(recording: dict[str, Any]) -> None:
    address = "postgresql+psycopg://private:secret@localhost/test"
    result = check.execute(Selection(("sample_records", "sample_accounts")), address)
    assert all(passed for _, passed in result)
    assert len(recording["runs"]) == 6
    assert recording["runs"][-1][1] == recording["runs"][-2][1]
    assert recording["runs"][-1][2]["APP_TEST_CONTROL_URL"] == address
    assert recording["runs"][-1][2]["APP_DEVELOPMENT_REPEAT_DATABASE"] == "1"
    assert recording["runs"][-2][2]["APP_DEVELOPMENT_REPEAT_DATABASE"] == "0"
    record = recording["records"][0]
    assert record["scope"] == {"kind": "modules", "modules": ["sample_records", "sample_accounts"]}
    assert len(record["timings"]) == 6 and record["elapsed_seconds"] >= 0
    assert "secret" not in json.dumps(record)
    assert recording["runs"][0][2]["APP_DISABLED_MODULES"] == "[]"


def test_quick_execution_records_non_acceptance_scope(recording: dict[str, Any]) -> None:
    check.execute(Selection(("sample_records",), quick=True), "")
    record = recording["records"][0]
    assert record["scope"]["kind"] == "quick"
    assert len(recording["runs"]) == 3
    assert recording["runs"][-1][2]["APP_DEVELOPMENT_MODULES"] == "[]"
    assert not any(title in record["checks"] for title in ("类型检查", "生成文档"))


def test_quick_success_does_not_replace_formal_failure() -> None:
    formal = {
        "fingerprints": {"sample_records": "v1"},
        "source_changed": False,
        "finished_at": "first",
        "scope": {"kind": "module"},
        "passed": False,
        "suites": [{"database": "sqlite", "exit_code": 1, "cases": []}],
    }
    quick = {**formal, "finished_at": "later", "scope": {"kind": "quick"}, "passed": True}
    status, cases = package_test_status([formal, quick], "sample_records", "v1")
    assert status["latest"]["sqlite"]["checks_passed"] is False
    assert cases == []


def test_missing_test_result_is_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "run", lambda *args: True)
    passed, evidence = check.run_tests("测试", ["-m", "pytest"], {}, "sqlite")
    assert passed is False and evidence["exit_code"] == 1


def test_matrix_clears_inherited_database(
    recording: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_TEST_DATABASE_URL", "postgresql://localhost/inherited")
    check.execute(Selection(), "postgresql://localhost/explicit")
    first, second = recording["records"][0]["suites"]
    assert [first["database"], second["database"]] == ["sqlite", "postgresql"]
    assert "APP_TEST_DATABASE_URL" not in recording["runs"][-2][2]
    assert recording["runs"][-1][2]["APP_TEST_CONTROL_URL"].endswith("/explicit")


def test_failed_primary_does_not_skip_template(
    recording: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = check.run_tests

    def failed(
        title: str, command: list[str], env: dict[str, str], database: str
    ) -> tuple[bool, dict[str, object]]:
        passed, evidence = original(title, command, env, database)
        return (False if title == "模块测试" else passed), evidence

    monkeypatch.setattr(check, "run_tests", failed)
    result = check.execute(Selection(("sample_records",)), "postgresql://localhost/test")
    assert not all(passed for _, passed in result)
    assert recording["runs"][-1][2]["APP_DEVELOPMENT_REPEAT_DATABASE"] == "0"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--quick"],
        ["--module", ""],
        ["--affected", "--module", "sample_records"],
        ["--affected", "--quick"],
    ],
)
def test_invalid_arguments_fail(arguments: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["fastapi_check.check", *arguments])
    with pytest.raises(SystemExit) as failure:
        check.arguments()
    assert failure.value.code == 2
