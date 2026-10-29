import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi_check.quality.rules import ROOT
from fastapi_project.development.design import design_doc
from fastapi_project.development.history import fingerprints, module_checks, read_checks, save_check
from fastapi_project.development.plan import check_plan
from fastapi_project.development.status import project_status
from fastapi_project.development.views import project_graph, project_markdown

from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES


def test_planned_packages_and_unplanned_modules(tmp_path: Path) -> None:
    plan = {
        "schema_version": 1,
        "name": "样例产品",
        "lines": [
            {
                "name": "文件业务",
                "packages": [
                    {
                        "module": "sample_records",
                        "title": "文件管理",
                        "operations": ["create_record", "future_record"],
                    },
                    {"module": "customer_contact", "title": "客户", "operations": ["save_contact"]},
                ],
            }
        ],
    }
    (tmp_path / "project-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    status = project_status(Catalog(MODULES), tmp_path, {"sample_records"})
    assert status["totals"] == {"planned": 3, "registered": 1, "test_successful": 0}
    assert status["ratios"]["registered"] == 0.3333
    assert status["unplanned_modules"] == ["sample_accounts"]
    packages = status["lines"][0]["packages"]
    assert packages[0]["missing"] == ["sample_records.future_record"]
    assert packages[0]["enabled"] is False
    assert packages[1]["missing"] == ["customer_contact.save_contact"]
    assert "登记 1/2" in project_graph(status)
    text = design_doc(Catalog(MODULES), tmp_path)
    assert "customer_contact.save_contact" in text and "未列入计划" in text


def test_missing_and_empty_plan_have_unknown_progress(tmp_path: Path) -> None:
    catalog = Catalog(MODULES)
    assert project_status(catalog, tmp_path)["totals"] is None
    (tmp_path / "project-plan.json").write_text(
        json.dumps({"schema_version": 1, "name": "新产品", "lines": []}), encoding="utf-8"
    )
    status = project_status(catalog, tmp_path)
    assert status["totals"] is None and status["ratios"] is None


@pytest.mark.parametrize(
    "operations", [[], ["create_record", "create_record"], ["other.create_record"], [1]]
)
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
                            {"module": "sample_records", "title": "文件", "operations": operations}
                        ],
                    }
                ],
            }
        )


def test_plan_dependencies_must_resolve_without_cycles() -> None:
    def plan(dependencies: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "name": "产品",
            "lines": [
                {
                    "name": "主线",
                    "packages": [
                        {
                            "module": name,
                            "title": name,
                            "kind": "capability",
                            "operations": ["run"],
                            "dependencies": targets,
                        }
                        for name, targets in dependencies.items()
                    ],
                }
            ],
        }

    check_plan(plan({"report_lists": ["source_records"], "source_records": []}))
    with pytest.raises(ValueError, match="计划外"):
        check_plan(plan({"report_lists": ["source_recordz"], "source_records": []}))
    with pytest.raises(ValueError, match="计划外"):
        check_plan(plan({"report_lists": ["report_lists"], "source_records": []}))
    with pytest.raises(ValueError, match="循环"):
        check_plan(plan({"alpha_lists": ["beta_lists"], "beta_lists": ["alpha_lists"]}))


def test_test_evidence_and_changed_source(tmp_path: Path) -> None:
    catalog = Catalog(MODULES)
    cases = [
        sample_case("passed", "ok"),
        sample_case("passed", "refused"),
        sample_case("failed", "ok"),
        sample_case("skipped", "ok"),
    ]
    codes = fingerprints(tmp_path, ["sample_records"])
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
    module = status["modules"]["sample_records"]
    assert module["tests"]["rounds"] == 1
    suite = module["tests"]["latest"]["sqlite"]
    assert suite["counts"] == {"passed": 2, "failed": 1, "skipped": 1}
    assert suite["checks_passed"] is False
    operation = next(
        item for item in module["operations"] if item["name"].endswith("create_record")
    )
    assert operation["test_executions"] == {"ok": 1, "refused": 1}
    code = tmp_path / "server/service/sample_records/new_step.py"
    code.parent.mkdir(parents=True)
    code.write_text("CHANGED = True\n", encoding="utf-8")
    module = project_status(catalog, tmp_path)["modules"]["sample_records"]
    assert not module["tests"]["latest"]["sqlite"]["current"]
    assert all(not item["test_executions"] for item in module["operations"])


def test_history_keeps_database_and_scope_separate() -> None:
    checks = [
        {
            "fingerprints": {"sample_records": "current"},
            "source_changed": False,
            "passed": True,
            "finished_at": "2026-10-05T00:00:00+00:00",
            "suites": [
                {"database": "sqlite", "exit_code": 0, "cases": []},
                {"database": "postgresql", "exit_code": 0, "cases": []},
            ],
        },
        {
            "fingerprints": {"sample_accounts": "other"},
            "source_changed": False,
            "passed": False,
            "finished_at": "2026-10-05T00:01:00+00:00",
            "suites": [],
        },
    ]
    result = module_checks(checks, "sample_records", "current")
    assert result["rounds"] == 1
    assert set(result["latest"]) == {"sqlite", "postgresql"}


def test_collected_rounds_are_deduplicated(tmp_path: Path) -> None:
    path = save_check(
        tmp_path,
        {
            "fingerprints": {"sample_records": "same"},
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


def test_pytest_records_real_outcomes(tmp_path: Path) -> None:
    tests = tmp_path / "test_outcomes.py"
    tests.write_text(
        "import pytest\ndef test_ok():\n    pass\ndef test_failed():\n    assert "
        "False\n@pytest.mark.skip(reason='样例跳过')\ndef test_skipped():\n    pass\n",
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


def test_runtime_sample_ratio_includes_missing_packages() -> None:
    from fastapi_project.development.status import runtime_progress

    status = {
        "lines": [
            {
                "packages": [
                    {"module": "sample_records", "planned": ["sample_records.create_record"]},
                    {"module": "future_package", "planned": ["future_package.calculate"]},
                ]
            }
        ],
        "runtime": {"available": True, "current_successful": ["sample_records.create_record"]},
    }
    runtime_progress(status, set())
    assert status["runtime"]["sample_ratio"] == 0.5
    runtime_progress(status, set(), "sample_records")
    assert status["runtime"]["sample_ratio"] == 1.0
    status["runtime"]["available"] = False
    runtime_progress(status, set())
    assert status["runtime"]["sample_ratio"] is None


def sample_case(outcome: str, status: str) -> dict[str, Any]:
    return {
        "nodeid": f"tests/integration/sample_records/test_files.py::{outcome}_{status}",
        "outcome": outcome,
        "runs": [{"operation": "sample_records.create_record", "status": status, "steps": []}],
    }
