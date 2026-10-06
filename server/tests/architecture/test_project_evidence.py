"""
摘要不能丢跨包失败、沿用旧证据，或让局部检查掩盖全量检查失败。
"""

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi_check.quality.rules import ROOT
from fastapi_project.development.commands import with_check_directories
from fastapi_project.development.history import fingerprints, save_check
from fastapi_project.development.status import project_status
from fastapi_project.development.summary import project_summary
from fastapi_project.development.summary import test_summary as summarize_tests

from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES


# 独立规则和源码只用于元数据检查，不执行任何业务写入。
def prepare(project: Path) -> None:
    doc = project / "doc/sample_records/rules.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "### R-01 文件规则\n\n| 样例编号 | 情况 | 结果 |\n"
        "| --- | --- | --- |\n| R-01-C01 | 指定文件 "
        "| 返回指定文件 |\n",
        encoding="utf-8",
    )
    for module in ("sample_records", "sample_accounts"):
        source = project / "server/service" / module / "source.py"
        source.parent.mkdir(parents=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
    test = project / "server/tests/integration/sample_accounts/test_call.py"
    test.parent.mkdir(parents=True)
    test.write_text("# 调用方测试第一版\n", encoding="utf-8")


# 调用方显式检查被调用模块的确认样例，setup失败时没有业务运行。
def case(name: str, outcome: str = "passed", *, runs: bool = True) -> dict[str, Any]:
    return {
        "nodeid": f"tests/integration/sample_accounts/test_call.py::{name}",
        "outcome": outcome,
        "scenario_ids": ["sample_records.R-01-C01"],
        "runs": [{"operation": "sample_records.get_record", "status": "ok", "steps": []}]
        if runs
        else [],
    }


# 记录输入中的范围明确，局部检查不能冒充完整框架检查。
def record(project: Path, cases: list[dict[str, Any]], *, scope: str = "all") -> None:
    names = [module.name for module in MODULES] if scope == "all" else [scope]
    passed = all(item["outcome"] == "passed" for item in cases)
    save_check(
        project,
        {
            "fingerprints": fingerprints(project, names),
            "source_changed": False,
            "passed": passed,
            "scope": {"kind": "all"} if scope == "all" else {"kind": "module", "module": scope},
            "checks": {"默认测试" if scope == "all" else "模块测试": passed},
            "suites": [{"database": "sqlite", "exit_code": 0 if passed else 1, "cases": cases}],
        },
    )


# setup失败没有run，但明确样例标记仍必须保留，不能被另一项通过遮住。
def test_cross_module_setup_failure_remains_scenario_failure(tmp_path: Path) -> None:
    prepare(tmp_path)
    record(tmp_path, [case("test_ok"), case("test_setup_error", "failed", runs=False)])
    status = project_status(Catalog(MODULES), tmp_path)
    item = status["modules"]["sample_records"]["scenarios"]["cases"][0]
    assert item["by_database"]["sqlite"]["status"] == "failed"
    assert len(item["by_database"]["sqlite"]["nodeids"]) == 2


# 只改调用方测试，也不能继续用它给被调用模块的样例提供当前通过证据。
def test_cross_module_evidence_checks_its_test_owner_version(tmp_path: Path) -> None:
    prepare(tmp_path)
    record(tmp_path, [case("test_ok")])
    source = tmp_path / "server/tests/integration/sample_accounts/test_call.py"
    source.write_text("# 调用方测试第二版\n", encoding="utf-8")
    status = project_status(Catalog(MODULES), tmp_path)
    evidence = status["modules"]["sample_records"]["scenarios"]["cases"][0]["by_database"]["sqlite"]
    assert evidence["current"] is False and evidence["status"] == "unrecorded"
    assert not status["modules"]["sample_records"]["operations"][1]["test_executions"]
    summary = project_summary(status)
    suite = summary["modules"]["sample_records"]["tests"]["latest"]["sqlite"]
    assert suite["counts"]["passed"] == 1  # 历史结果保留，不冒充当前证据。
    assert suite["current_counts"]["passed"] == 0 and suite["stale_count"] == 1
    assert suite["problems"][0]["current"] is False
    assert any(item["kind"] == "stale_source" for item in summary["attention"])


# 完整检查失败后，各包单独通过仍须报告框架失败，并保留失败测试入口。
def test_local_success_does_not_hide_full_framework_failure(tmp_path: Path) -> None:
    prepare(tmp_path)
    failed = {
        "nodeid": "tests/framework/test_global.py::test_framework",
        "outcome": "failed",
        "runs": [],
    }
    record(tmp_path, [failed])
    for name in ("sample_records", "sample_accounts"):
        record(
            tmp_path,
            [
                {
                    "nodeid": f"tests/integration/{name}/test_local.py::test_ok",
                    "outcome": "passed",
                    "runs": [],
                }
            ],
            scope=name,
        )
    result = project_summary(project_status(Catalog(MODULES), tmp_path))
    assert result["latest_check"]["passed"] is True
    assert result["latest_full_check"]["passed"] is False
    assert any("全量检查" in item["message"] for item in result["attention"])
    assert "test_framework" in json.dumps(result["latest_full_check"])


# 调用操作标题数量增长不应进入项目级摘要；具体标题只在单包查看。
def test_dependency_titles_do_not_expand_project_summary(tmp_path: Path) -> None:
    prepare(tmp_path)
    status = project_status(Catalog(MODULES), tmp_path)
    before = len(json.dumps(project_summary(status)))
    status["dependencies"] = {
        "sample_records": {"sample_accounts": [f"title_{i}" for i in range(20000)]}
    }
    result = project_summary(status)
    assert len(json.dumps(result)) < before + 1000
    assert "title_19999" not in json.dumps(result)


# 大量过期通过记录在前时，真正失败仍须优先进入有限预览。
@pytest.mark.parametrize("outcome", ["passed", "skipped"])
def test_failure_preview_precedes_stale_successes(tmp_path: Path, outcome: str) -> None:
    prepare(tmp_path)
    record(
        tmp_path,
        [*[case(f"test_old_{i}", outcome) for i in range(6)], case("test_failed", "failed")],
    )
    source = tmp_path / "server/service/sample_records/source.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    tests = project_status(Catalog(MODULES), tmp_path)["modules"]["sample_records"]["tests"]
    suite = summarize_tests(tests)["latest"]["sqlite"]
    assert suite["problems"][0]["outcome"] == "failed"
    assert suite["problems"][0]["nodeid"].endswith("test_failed")
    assert suite["problem_count"] == 7 and suite["omitted_problems"] == 2


# 外部检查目录是证据来源，摘要给出的继续读取命令必须保留它。
def test_imported_check_next_command_keeps_its_source_directory(tmp_path: Path) -> None:
    prepare(tmp_path)
    record(tmp_path, [case("test_imported_failure", "failed", runs=False)])
    source = tmp_path / "server/var/development/checks"
    folder = tmp_path / "imported-checks"
    folder.mkdir()
    for path in source.glob("*.json"):
        path.rename(folder / path.name)
    status = project_summary(project_status(Catalog(MODULES), tmp_path, extra_checks=[folder]))
    status = with_check_directories(status, [folder])
    module = status["modules"]["sample_accounts"]
    command = module["tests"]["latest"]["sqlite"]["problems"][0]["next"]
    assert "--checks" in shlex.split(command)
    follow = subprocess.run(
        shlex.split(command), cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert follow.returncode == 0, follow.stderr
    assert json.loads(follow.stdout)["nodeid"].endswith("test_imported_failure")
