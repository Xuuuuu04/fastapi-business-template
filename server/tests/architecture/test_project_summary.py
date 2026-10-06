"""
主代理先读摘要，问题和未实现目标仍可见，详细证据按准确入口读取。
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES
from tools.development.history import fingerprints, read_checks, save_check
from tools.development.status import project_status
from tools.development.summary import (
    project_summary,
    selected_operation,
    selected_test,
    summary_markdown,
)
from tools.quality.rules import ROOT


# 长运行与框架失败样例用于检查摘要保留问题但省略运行详情。
def sample_cases() -> list[dict[str, Any]]:
    cases = [
        {
            "nodeid": f"tests/integration/sample_records/test_sample.py::test_{number}",
            "outcome": "failed" if number < 8 else "passed",
            "runs": [
                {
                    "operation": "sample_records.create_record",
                    "status": "ok",
                    "steps": [],
                    "detail": "DETAIL_ONLY" * 1000,
                }
            ],
        }
        for number in range(20)
    ]
    cases.append(
        {
            "nodeid": "tests/framework/test_example.py::test_framework",
            "outcome": "failed",
            "runs": [],
        }
    )
    return cases


# 独立计划包含未实现目标，长运行内容仅用于检查摘要不会把详情带进去。
def sample_status(tmp_path: Path) -> dict[str, Any]:
    plan = {
        "schema_version": 1,
        "name": "样例产品",
        "lines": [
            {
                "name": "文件业务",
                "packages": [
                    {
                        "module": "sample_records",
                        "title": "文件",
                        "operations": ["create_record", "future_record"],
                    },
                    {"module": "future_package", "title": "未来包", "operations": ["prepare"]},
                ],
            }
        ],
    }
    (tmp_path / "project-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    folder = tmp_path / "doc/sample_records"
    folder.mkdir(parents=True)
    (folder / "rules.md").write_text(
        "# 文件\n\n### R-01 测试规则\n\n业务期限：待确认。\n", encoding="utf-8"
    )
    cases = sample_cases()
    save_check(
        tmp_path,
        {
            "fingerprints": fingerprints(tmp_path, [m.name for m in MODULES]),
            "source_changed": False,
            "passed": False,
            "checks": {"类型检查": False, "默认测试": False},
            "suites": [{"database": "sqlite", "exit_code": 1, "cases": cases}],
        },
    )
    return project_status(Catalog(MODULES), tmp_path, {"sample_accounts"})


# 摘要减少输入，但不能删掉失败、禁用、待确认和未实现目标。
def test_summary_is_small_and_keeps_decision_facts(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    before = copy.deepcopy(status)
    result = project_summary(status)
    output = json.dumps(result, ensure_ascii=False)
    assert len(output) < 20000 and len(output) < len(json.dumps(status)) / 10
    assert "DETAIL_ONLY" not in output
    assert result["latest_check"]["passed"] is False
    assert result["latest_check"]["checks"]["类型检查"] is False
    assert result["modules"]["sample_accounts"]["enabled"] is False
    assert result["modules"]["sample_records"]["pending"]
    assert result["lines"][0]["packages"][0]["missing"] == ["sample_records.future_record"]
    assert result["lines"][0]["packages"][1]["missing"] == ["future_package.prepare"]
    assert status == before


# 问题只预览少量，失败总数和准确继续入口必须保留。
def test_problem_list_is_bounded_but_counts_and_next_steps_remain(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    suite = project_summary(status)["modules"]["sample_records"]["tests"]["latest"]["sqlite"]
    assert suite["counts"] == {"passed": 12, "failed": 8, "skipped": 0}
    assert suite["problem_count"] == 8 and suite["omitted_problems"] == 3
    assert len(suite["problems"]) == 5
    assert "--test" in suite["problems"][0]["next"]
    global_suite = status["latest_check"]["suites"]["sqlite"]
    assert global_suite["counts"]["failed"] == 9
    assert global_suite["problem_count"] == 9
    assert "current" not in global_suite


# 源码变化后摘要必须提醒过期，操作不沿用旧成功。
def test_changed_source_is_visible_in_summary(tmp_path: Path) -> None:
    sample_status(tmp_path)
    code = tmp_path / "server/service/sample_records/store.py"
    code.parent.mkdir(parents=True)
    code.write_text("VALUE = 'changed'\n", encoding="utf-8")
    status = project_status(Catalog(MODULES), tmp_path)
    result = project_summary(status)
    module = result["modules"]["sample_records"]
    assert not module["tests"]["latest"]["sqlite"]["current"]
    assert module["operation_count"] == 5 and "operations" not in module
    assert all(
        not item["test_executions"]
        for item in project_summary(status, "sample_records")["operations"]
    )
    assert "过期" in summary_markdown(result)


# 按需入口只展开所选范围，不重复其他操作详情。
def test_module_and_operation_views_do_not_expand_other_operations(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    result = project_summary(status, "sample_records")
    assert result["view"] == "summary" and "modules" not in result
    assert len(result["operations"]) == 5
    operation = selected_operation(status, "sample_records.create_record")
    assert operation["module"] == "sample_records"
    assert operation["name"] == "sample_records.create_record"
    assert operation["steps"] and "graph" in operation
    assert "operations" not in operation
    with pytest.raises(ValueError, match="尚未登记"):
        selected_operation(status, "sample_records.future_record")


# 单测试入口保留框架失败，并避免跨模块重复记录。
def test_test_view_includes_global_failures_without_duplicate_records(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    nodeid = "tests/framework/test_example.py::test_framework"
    result = selected_test(status, nodeid, "", read_checks(tmp_path))
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["case"]["outcome"] == "failed" and record["checks_passed"] is False
    assert all(item["current"] for item in record["modules"].values())
    with pytest.raises(ValueError, match="没有测试记录"):
        selected_test(status, "missing", "", read_checks(tmp_path))


# 检查期间源码改变，该轮所有模块证据均不能记为当前。
def test_test_view_never_marks_changed_during_check_as_current(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    checks = read_checks(tmp_path)
    checks[0]["source_changed"] = True
    result = selected_test(status, "tests/framework/test_example.py::test_framework", "", checks)
    assert result["records"][0]["source_changed"] is True
    assert all(not item["current"] for item in result["records"][0]["modules"].values())


# 数据库摘要只保留运行入口，不展开执行详情。
def test_optional_runtime_summary_keeps_ids_without_execution_payloads(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    status["runtime"] = {
        "available": True,
        "graph": "FULL_GRAPH",
        "runs": [
            {
                "id": "one",
                "operation": "sample_records.create_record",
                "status": "ok",
                "steps": ["DETAIL_ONLY"],
            }
        ],
    }
    result = project_summary(status)
    assert result["runtime"]["runs"] == [
        {"id": "one", "operation": "sample_records.create_record", "status": "ok"}
    ]
    assert "FULL_GRAPH" not in json.dumps(result)
    assert "DETAIL_ONLY" not in json.dumps(result)


# 真实CLI只读源码和已有记录，默认及摘要均不连接数据库。
def test_real_cli_keeps_old_json_and_does_not_open_database(tmp_path: Path) -> None:
    database = tmp_path / "must-not-open.db"
    env = {**os.environ, "APP_DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    for args, view in (
        (["--json"], None),
        (["--summary", "--json"], "summary"),
    ):
        run = subprocess.run(
            [sys.executable, "-m", "tools.project", *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        result = json.loads(run.stdout)
        if view is None:
            assert "modules" in result and "module_graph" in result and "view" not in result
        else:
            assert result["view"] == view
    assert not database.exists()


# 互斥视图、错误模块和无效运行数量必须明确失败。
@pytest.mark.parametrize(
    "args",
    [
        ["--summary", "--operation", "sample_records.create_record"],
        ["--operation", "sample_records.create_record", "--module", "sample_accounts"],
        ["--test", "sample", "--runs"],
        ["--summary", "--limit", "0"],
    ],
)
def test_real_cli_rejects_ambiguous_or_invalid_scope(args: list[str]) -> None:
    run = subprocess.run(
        [sys.executable, "-m", "tools.project", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 2 and "error" in run.stderr


# 被调用能力或其规则改变时，直接、间接调用方的旧结果都过期，无关模块不受影响。
def test_dependency_versions_include_transitive_providers(tmp_path: Path) -> None:
    names = ["request_handler", "middle_service", "record_provider", "other_package"]
    for name in names:
        source = tmp_path / "server/service" / name / "flow.py"
        source.parent.mkdir(parents=True)
        source.write_text("VERSION = 1\n", encoding="utf-8")
    links = {
        "request_handler": {"middle_service": ["直接调用"]},
        "middle_service": {"record_provider": ["后台任务：保存"]},
    }
    before = fingerprints(tmp_path, names, links)
    source = tmp_path / "server/service/record_provider/flow.py"
    source.write_text("VERSION = 2\n", encoding="utf-8")
    after = fingerprints(tmp_path, names, links)
    assert all(before[name] != after[name] for name in names[:3])
    assert before["other_package"] == after["other_package"]


# 依赖表即使包含重复或循环，也只计算一次路径；缺省依赖保留旧独立用法。
def test_dependency_versions_are_finite_and_optional(tmp_path: Path) -> None:
    from tools.development.history import dependency_modules

    links = {
        "first_package": {"second_package": ["调用"]},
        "second_package": {"first_package": ["调用"]},
    }
    assert dependency_modules("first_package", links) == ["first_package", "second_package"]
    assert fingerprints(tmp_path, ["first_package"]) == fingerprints(
        tmp_path, ["first_package"], {}
    )


# 大计划只给数量与缺项预览，单包入口保留全部目标且不伪造已登记代码。
def test_large_plan_is_previewed_and_missing_package_can_be_opened(tmp_path: Path) -> None:
    status = sample_status(tmp_path)
    package = status["lines"][0]["packages"][1]
    package["planned"] = [f"future_package.prepare_{number}" for number in range(100)]
    package["missing"] = package["planned"]
    preview = project_summary(status)["lines"][0]["packages"][1]
    assert preview["counts"]["missing"] == 100
    assert len(preview["missing"]) == 5 and preview["omitted_missing"] == 95
    details = project_summary(status, "future_package")
    assert details["registered"] is False and len(details["plan"]["missing"]) == 100
    assert "代码尚未登记" in summary_markdown(details)
    with pytest.raises(ValueError, match="未列入计划"):
        project_summary(status, "unknown_package")
