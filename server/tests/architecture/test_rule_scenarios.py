import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi_check.quality.rules import ROOT
from fastapi_project.development.history import module_checks
from fastapi_project.development.scenarios import scenario_status

TABLE = "### R-05 会话\n\n| 样例编号 | 情况 | 结果 |\n| --- | --- | --- |\n"
PYTEST_SOURCE = """import pytest

@pytest.fixture
def setup_error():
    raise RuntimeError("setup failed")

@pytest.fixture
def teardown_error():
    yield
    raise RuntimeError("teardown failed")

@pytest.mark.parametrize("behavior", [
    pytest.param("pass", id="normal", marks=[pytest.mark.rule_case("demo.R-05-C01"),
                                           pytest.mark.rule_case("demo.R-05-C09")]),
    pytest.param("fail", id="failure", marks=pytest.mark.rule_case("demo.R-05-C02")),
    pytest.param("skip", id="skip", marks=pytest.mark.rule_case("demo.R-05-C03")),
    pytest.param("fail", id="xfail", marks=[pytest.mark.rule_case("demo.R-05-C04"),
                                         pytest.mark.xfail(reason="expected")]),
    pytest.param("pass", id="xpass", marks=[pytest.mark.rule_case("demo.R-05-C05"),
                                         pytest.mark.xfail(reason="expected")]),
    pytest.param("pass", id="strict_xpass", marks=[pytest.mark.rule_case("demo.R-05-C10"),
                                                pytest.mark.xfail(strict=True)]),
])
def test_parameter(behavior):
    secret = "must-not-record-secret"
    if behavior == "skip":
        pytest.skip("not available")
    assert behavior != "fail"

@pytest.mark.rule_case("demo.R-05-C06")
def test_setup(setup_error):
    pass

@pytest.mark.rule_case("demo.R-05-C07")
def test_teardown(teardown_error):
    pass

@pytest.mark.rule_case("demo.R-05-C08")
def test_skip_then_teardown_error(teardown_error):
    pytest.skip("call skipped")
"""


def write_rules(project: Path, text: str = TABLE) -> Path:
    path = project / "doc/demo/rules.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def recorded(identity: str | None, outcome: str = "passed", nodeid: str = "test.py::case") -> Any:
    case = {"nodeid": nodeid, "outcome": outcome, "runs": []}
    if identity is not None:
        case["scenario_ids"] = [f"demo.{identity}"]
    return case


def suite(cases: list[Any], current: bool = True, exit_code: int = 0) -> dict[str, Any]:
    return {"current": current, "exit_code": exit_code, "checks_passed": False, "cases": cases}


@pytest.mark.parametrize(
    "text", ["", "### R-05 会话\n| 情况 | 结果 |\n| --- | --- |\n| 旧值 | 拒绝 |"]
)
def test_legacy_tables_do_not_declare_scenarios(tmp_path: Path, text: str) -> None:
    write_rules(tmp_path, text)
    result = scenario_status(tmp_path, "demo", {"latest": {}})
    assert not result["declared"] and not result["cases"]
    assert "没有声明不等于没有规则" in result["note"]


@pytest.mark.parametrize(
    "text",
    [
        TABLE + "| R-05-C01 | 输入 | 拒绝 |\n| R-05-C01 | 输入 | 拒绝 |",
        TABLE + "| R-06-C01 | 输入 | 拒绝 |",
        TABLE + "| C01 | 输入 | 拒绝 |",
        TABLE + "| R-05-C01 | 输入 | |",
        TABLE + "| R-05-C01 | 输入 | 拒绝 | 多余 |",
        TABLE.replace("| --- | --- | --- |", "| --- | --- |"),
        TABLE.replace("| --- | --- | --- |", "| --- | --- | --- | extra"),
        TABLE.replace("| 样例编号 | 情况 | 结果 |", "| 样例编号 | 情况 | 结果 | extra"),
        TABLE + "| R-05-C01 | 输入 | 拒绝",
        TABLE.replace("样例编号 | 情况", "情况 | 样例编号"),
        TABLE.replace("### R-05 会话", "# 其他内容") + "| R-05-C01 | 输入 | 拒绝 |",
    ],
)
def test_invalid_tables_raise(tmp_path: Path, text: str) -> None:
    write_rules(tmp_path, text)
    with pytest.raises(ValueError):
        scenario_status(tmp_path, "demo", {})


def test_current_database_evidence_and_unknown_ids(tmp_path: Path) -> None:
    write_rules(
        tmp_path,
        TABLE + "| R-05-C01 | 输入\\|条件 | 返回\\|结果 |\n| R-05-C02 | 另一个输入 | 拒绝 |",
    )
    cases = [recorded("R-05-C01"), recorded(None), recorded("R-05-C99")]
    cases.append({"nodeid": "test_R_05_C02", "outcome": "passed", "runs": []})
    tests = {"latest": {"sqlite": suite(cases, exit_code=1), "postgresql": suite(cases, False)}}
    result = scenario_status(tmp_path, "demo", tests)
    first, second = result["cases"]
    assert (first["id"], first["rule"], first["title"], first["expected"]) == (
        "demo.R-05-C01",
        "R-05",
        "输入|条件",
        "返回|结果",
    )
    assert first["by_database"]["sqlite"]["status"] == "passed"
    assert first["by_database"]["sqlite"]["nodeids"] == ["test.py::case"]
    assert first["by_database"]["postgresql"]["status"] == "unrecorded"
    assert second["by_database"]["sqlite"]["status"] == "unrecorded"
    assert result["counts_by_database"]["sqlite"] == {
        "planned": 2,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "unrecorded": 1,
    }
    assert result["unknown_ids"] == ["demo.R-05-C99"]
    assert not result["checks_by_database"]["sqlite"]["suite_passed"]
    assert not result["checks_by_database"]["sqlite"]["checks_passed"]


@pytest.mark.parametrize(
    "outcome,status", [("failed", "failed"), ("skipped", "skipped"), ("unrecorded", "unrecorded")]
)
def test_all_matching_cases_are_accounted_for(tmp_path: Path, outcome: str, status: str) -> None:
    write_rules(tmp_path, TABLE + "| R-05-C01 | 输入 | 结果 |")
    cases = [recorded("R-05-C01"), recorded("R-05-C01", outcome, "test.py::other")]
    result = scenario_status(tmp_path, "demo", {"latest": {"sqlite": suite(cases)}})
    evidence = result["cases"][0]["by_database"]["sqlite"]
    assert evidence["status"] == status and len(evidence["nodeids"]) == 2


def test_source_changed_is_explicit(tmp_path: Path) -> None:
    write_rules(tmp_path, TABLE + "| R-05-C01 | 输入 | 结果 |")
    checks = [
        {
            "fingerprints": {"demo": "same"},
            "source_changed": True,
            "passed": True,
            "finished_at": "2026-10-05",
            "suites": [{"database": "sqlite", "exit_code": 0, "cases": [recorded("R-05-C01")]}],
        }
    ]
    tests = module_checks(checks, "demo", "same")
    result = scenario_status(tmp_path, "demo", tests)
    assert result["checks_by_database"]["sqlite"]["source_changed"] is True
    assert result["cases"][0]["by_database"]["sqlite"]["status"] == "unrecorded"


def run_pytest(
    folder: Path, source: str, *options: str
) -> tuple[subprocess.CompletedProcess[str], Any]:
    tests = folder / "test_evidence.py"
    tests.write_text(source, encoding="utf-8")
    output = folder / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-c",
            str(ROOT / "pyproject.toml"),
            "--confcutdir",
            str(folder),
            "-p",
            "tests.development_history",
            *options,
            str(tests),
        ],
        cwd=ROOT,
        env={**os.environ, "APP_DEVELOPMENT_RESULT": str(output)},
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_pytest_collection_is_not_pass_evidence(tmp_path: Path) -> None:
    result, evidence = run_pytest(tmp_path, PYTEST_SOURCE, "--collect-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert evidence["cases"] == []
    result, evidence = run_pytest(
        tmp_path, "import pytest\n@pytest.mark.not_registered\ndef test_unknown(): pass\n"
    )
    assert result.returncode == 2 and evidence["cases"] == []


def test_pytest_real_phase_outcomes(tmp_path: Path) -> None:
    result, evidence = run_pytest(tmp_path, PYTEST_SOURCE)
    assert result.returncode == evidence["exit_code"] == 1
    cases = {case["scenario_ids"][0]: case for case in evidence["cases"]}
    expected = {
        1: "passed",
        2: "failed",
        3: "skipped",
        4: "skipped",
        5: "skipped",
        6: "failed",
        7: "failed",
        8: "failed",
        10: "failed",
    }
    assert {identity: case["outcome"] for identity, case in cases.items()} == {
        f"demo.R-05-C{number:02}": status for number, status in expected.items()
    }
    assert cases["demo.R-05-C01"]["scenario_ids"] == ["demo.R-05-C01", "demo.R-05-C09"]
    assert cases["demo.R-05-C04"]["xfail"] == "xfailed"
    assert cases["demo.R-05-C05"]["xfail"] == "xpassed"
    assert cases["demo.R-05-C06"]["phases"]["setup"] == "failed"
    assert cases["demo.R-05-C07"]["phases"] == {
        "setup": "passed",
        "call": "passed",
        "teardown": "failed",
    }
    assert cases["demo.R-05-C08"]["phases"]["call"] == "skipped"
    assert "must-not-record-secret" not in json.dumps(evidence)
    check_recorded_mapping(tmp_path, evidence)


def check_recorded_mapping(tmp_path: Path, evidence: dict[str, Any]) -> None:
    write_rules(
        tmp_path,
        TABLE
        + "\n".join(
            f"| R-05-C{number:02} | 输入 {number} | 结果 {number} |" for number in range(1, 11)
        ),
    )
    mapped = scenario_status(
        tmp_path, "demo", {"latest": {"sqlite": suite(evidence["cases"], exit_code=1)}}
    )
    assert mapped["counts_by_database"]["sqlite"] == {
        "planned": 10,
        "passed": 2,
        "failed": 5,
        "skipped": 3,
        "unrecorded": 0,
    }
    assert (
        mapped["cases"][8]["by_database"]["sqlite"]["nodeids"]
        == (mapped["cases"][0]["by_database"]["sqlite"]["nodeids"])
    )
    assert not mapped["checks_by_database"]["sqlite"]["suite_passed"]


@pytest.mark.parametrize("marker", ["rule_case()", "rule_case('R-05-C01')", "rule_case(5)"])
def test_pytest_rejects_invalid_rule_case(tmp_path: Path, marker: str) -> None:
    result, evidence = run_pytest(
        tmp_path, f"import pytest\n@pytest.mark.{marker}\ndef test_bad_marker(): pass\n"
    )
    assert result.returncode == 4 and evidence["cases"] == []
