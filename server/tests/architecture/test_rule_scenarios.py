"""
确认样例只使用规则表预期与真实 pytest 标记，不把注释、旧结果或整轮失败当成通过。
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.development.history import module_checks
from tools.development.scenarios import scenario_status
from tools.quality.rules import ROOT

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


# 临时业务文档保留预期的唯一来源。
def write_rules(project: Path, text: str = TABLE) -> Path:
    path = project / "doc/demo/rules.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# 测试记录只含名称、状态和样例编号，不包含业务取值。
def recorded(identity: str | None, outcome: str = "passed", nodeid: str = "test.py::case") -> Any:
    case = {"nodeid": nodeid, "outcome": outcome, "runs": []}
    if identity is not None:
        case["scenario_ids"] = [f"demo.{identity}"]
    return case


# 每个数据库独立保留当前性和整轮结果。
def suite(cases: list[Any], current: bool = True, exit_code: int = 0) -> dict[str, Any]:
    return {"current": current, "exit_code": exit_code, "checks_passed": False, "cases": cases}


# 没有样例列的老模块照常返回，没有声明不能被解释为没有规则。
@pytest.mark.parametrize(
    "text", ["", "### R-05 会话\n| 情况 | 结果 |\n| --- | --- |\n| 旧值 | 拒绝 |"]
)
def test_legacy_tables_do_not_declare_scenarios(tmp_path: Path, text: str) -> None:
    write_rules(tmp_path, text)
    result = scenario_status(tmp_path, "demo", {"latest": {}})
    assert not result["declared"] and not result["cases"]
    assert "没有声明不等于没有规则" in result["note"]


# ID、所属规则、表列和分隔行错误必须可见，不能悄悄丢弃。
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


# 当前证据与整轮失败分开；过期结果、老记录和只写规则注释的测试不增加通过数。
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


# 一个样例被多个测试标记时，不能选择性只展示通过的测试。
@pytest.mark.parametrize(
    "outcome,status", [("failed", "failed"), ("skipped", "skipped"), ("unrecorded", "unrecorded")]
)
def test_all_matching_cases_are_accounted_for(tmp_path: Path, outcome: str, status: str) -> None:
    write_rules(tmp_path, TABLE + "| R-05-C01 | 输入 | 结果 |")
    cases = [recorded("R-05-C01"), recorded("R-05-C01", outcome, "test.py::other")]
    result = scenario_status(tmp_path, "demo", {"latest": {"sqlite": suite(cases)}})
    evidence = result["cases"][0]["by_database"]["sqlite"]
    assert evidence["status"] == status and len(evidence["nodeids"]) == 2


# 检查期间源码改变必须显示，不能仅用整轮通过掩盖当前性。
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


# 子进程使用真实插件和项目严格配置，不加载上层业务夹具。
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


# 真正收集参数化测试不等于执行通过；未注册标记仍被 strict-markers 拒绝。
def test_pytest_collection_is_not_pass_evidence(tmp_path: Path) -> None:
    result, evidence = run_pytest(tmp_path, PYTEST_SOURCE, "--collect-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert evidence["cases"] == []
    result, evidence = run_pytest(
        tmp_path, "import pytest\n@pytest.mark.not_registered\ndef test_unknown(): pass\n"
    )
    assert result.returncode == 2 and evidence["cases"] == []


# 真正参数化的每个 item 独立保存 ID；所有阶段的失败与 xfail 都不能冒充 pass。
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


# 使用同一次真实执行验证样例统计，避免另造通过证据。
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


# 显式标记也必须只有一个完整编号，错误不能被吞掉。
@pytest.mark.parametrize("marker", ["rule_case()", "rule_case('R-05-C01')", "rule_case(5)"])
def test_pytest_rejects_invalid_rule_case(tmp_path: Path, marker: str) -> None:
    result, evidence = run_pytest(
        tmp_path, f"import pytest\n@pytest.mark.{marker}\ndef test_bad_marker(): pass\n"
    )
    assert result.returncode == 4 and evidence["cases"] == []
