"""
开发视图的完成条件：预先计划不能由当前代码猜出，测试标注不能冒充实际通过，
旧版本与失败测试不能提高当前代码的成功执行数量。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.setup.catalog import MODULES
from shared.modules.catalog import Catalog
from tools.development.design import design_doc
from tools.development.history import fingerprints, module_checks, read_checks, save_check
from tools.development.plan import check_plan
from tools.development.status import project_status
from tools.development.views import project_graph, project_markdown
from tools.quality.rules import ROOT


# 在真实模块之外预先设计另一个开发包，它应显示未实现而不是消失。
def test_planned_packages_and_unplanned_modules(tmp_path: Path) -> None:
    plan = {
        "schema_version": 1,
        "name": "样例产品",
        "lines": [
            {
                "name": "文件业务",
                "packages": [
                    {
                        "module": "file_library",
                        "title": "文件管理",
                        "operations": ["save_file", "future_file"],
                    },
                    {"module": "customer_contact", "title": "客户", "operations": ["save_contact"]},
                ],
            }
        ],
    }
    (tmp_path / "project-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    status = project_status(Catalog(MODULES), tmp_path, {"file_library"})
    assert status["totals"] == {"planned": 3, "registered": 1, "test_successful": 0}
    assert status["ratios"]["registered"] == 0.3333
    assert status["unplanned_modules"] == ["user_access"]
    packages = status["lines"][0]["packages"]
    assert packages[0]["missing"] == ["file_library.future_file"]
    assert packages[0]["enabled"] is False
    assert packages[1]["missing"] == ["customer_contact.save_contact"]
    assert "登记 1/2" in project_graph(status)
    text = design_doc(Catalog(MODULES), tmp_path)
    assert "customer_contact.save_contact" in text and "未列入计划" in text


# 没有目标或目标为空时比例未知，不能用已存在的代码冒充整个产品已经完成。
def test_missing_and_empty_plan_have_unknown_progress(tmp_path: Path) -> None:
    catalog = Catalog(MODULES)
    assert project_status(catalog, tmp_path)["totals"] is None
    (tmp_path / "project-plan.json").write_text(
        json.dumps({"schema_version": 1, "name": "新产品", "lines": []}), encoding="utf-8"
    )
    status = project_status(catalog, tmp_path)
    assert status["totals"] is None and status["ratios"] is None


# 重复开发包、空操作和重复操作都会使比例失去意义，应拒绝读取。
@pytest.mark.parametrize("operations", [[], ["save_file", "save_file"], ["other.save_file"], [1]])
def test_invalid_design_is_visible(operations: list[Any]) -> None:
    with pytest.raises(ValueError):
        check_plan(
            {
                "schema_version": 1,
                "name": "产品",
                "lines": [
                    {
                        "name": "文件",
                        "packages": [
                            {"module": "file_library", "title": "文件", "operations": operations}
                        ],
                    }
                ],
            }
        )


# 当前代码仅计入通过测试中的成功运行，拒绝、跳过和失败测试中的运行单独保留。
def test_test_evidence_and_changed_source(tmp_path: Path) -> None:
    catalog = Catalog(MODULES)
    cases = [
        sample_case("passed", "ok"),
        sample_case("passed", "refused"),
        sample_case("failed", "ok"),
        sample_case("skipped", "ok"),
    ]
    codes = fingerprints(tmp_path, ["file_library"])
    save_check(
        tmp_path,
        {
            "fingerprints": codes,
            "source_changed": False,
            "passed": False,
            "checks": {"默认测试": False},
            "suites": [{"database": "sqlite", "exit_code": 1, "cases": cases}],
        },
    )
    status = project_status(catalog, tmp_path)
    assert "失败项目：默认测试" in project_markdown(status)
    module = status["modules"]["file_library"]
    assert module["tests"]["rounds"] == 1
    suite = module["tests"]["latest"]["sqlite"]
    assert suite["counts"] == {"passed": 2, "failed": 1, "skipped": 1}
    assert suite["checks_passed"] is False
    operation = next(item for item in module["operations"] if item["name"].endswith("save_file"))
    assert operation["test_executions"] == {"ok": 1, "refused": 1}
    code = tmp_path / "server/service/file_library/new_step.py"
    code.parent.mkdir(parents=True)
    code.write_text("CHANGED = True\n", encoding="utf-8")
    module = project_status(catalog, tmp_path)["modules"]["file_library"]
    assert not module["tests"]["latest"]["sqlite"]["current"]
    assert all(not item["test_executions"] for item in module["operations"])


# SQLite 与 PostgreSQL 分开取最近结果，不把一次数据库测试算成两轮完整检查。
def test_history_keeps_database_and_scope_separate() -> None:
    checks = [
        {
            "fingerprints": {"file_library": "current"},
            "source_changed": False,
            "passed": True,
            "finished_at": "2026-10-05T00:00:00+00:00",
            "suites": [
                {"database": "sqlite", "exit_code": 0, "cases": []},
                {"database": "postgresql", "exit_code": 0, "cases": []},
            ],
        },
        {
            "fingerprints": {"user_access": "other"},
            "source_changed": False,
            "passed": False,
            "finished_at": "2026-10-05T00:01:00+00:00",
            "suites": [],
        },
    ]
    result = module_checks(checks, "file_library", "current")
    assert result["rounds"] == 1
    assert set(result["latest"]) == {"sqlite", "postgresql"}


# 同一轮从分支与 CI 多次收集也只能计算一次，变过代码的轮次明确过期。
def test_collected_rounds_are_deduplicated(tmp_path: Path) -> None:
    path = save_check(
        tmp_path,
        {
            "fingerprints": {"file_library": "same"},
            "source_changed": True,
            "passed": True,
            "suites": [],
        },
    )
    imported = tmp_path / "ci"
    imported.mkdir()
    shutil.copy2(path, imported / path.name)
    checks = read_checks(tmp_path, [imported])
    assert len(checks) == 1
    assert checks[0]["source_changed"] is True


# 真实 pytest 的通过、失败和跳过被分别记录；返回值不会被通过数量掩盖。
def test_pytest_records_real_outcomes(tmp_path: Path) -> None:
    tests = tmp_path / "test_outcomes.py"
    tests.write_text(
        "import pytest\ndef test_ok():\n    pass\ndef test_failed():\n    assert False\n"
        "@pytest.mark.skip(reason='样例跳过')\ndef test_skipped():\n    pass\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"
    env = {**os.environ, "APP_DEVELOPMENT_RESULT": str(output)}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--confcutdir",
            str(tmp_path),
            "-p",
            "tests.development_history",
            str(tests),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    recorded = json.loads(output.read_text(encoding="utf-8"))
    assert recorded["exit_code"] == 1
    assert [case["outcome"] for case in recorded["cases"]] == ["passed", "failed", "skipped"]


# 近期样例比例包含计划中未实现的操作，无数据库证据时保持未知。
def test_runtime_sample_ratio_includes_missing_packages() -> None:
    from tools.development.status import runtime_progress

    status = {
        "lines": [
            {
                "packages": [
                    {"module": "file_library", "planned": ["file_library.save_file"]},
                    {"module": "future_package", "planned": ["future_package.calculate"]},
                ]
            }
        ],
        "runtime": {"available": True, "current_successful": ["file_library.save_file"]},
    }
    runtime_progress(status, set())
    assert status["runtime"]["sample_ratio"] == 0.5
    runtime_progress(status, set(), "file_library")
    assert status["runtime"]["sample_ratio"] == 1.0
    status["runtime"]["available"] = False
    runtime_progress(status, set())
    assert status["runtime"]["sample_ratio"] is None


# 一条测试样例可以模拟运行状态，不携带业务取值。
def sample_case(outcome: str, status: str) -> dict[str, Any]:
    return {
        "nodeid": f"tests/integration/file_library/test_files.py::{outcome}_{status}",
        "outcome": outcome,
        "runs": [{"operation": "file_library.save_file", "status": status, "steps": []}],
    }
