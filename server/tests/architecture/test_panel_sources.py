import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi_project.development import check_storage
from fastapi_project.development.history import module_checks, read_checks, save_check
from fastapi_project.development.panel_dependencies import dependency_issues
from fastapi_project.development.panel_duplicates import duplicate_hints
from fastapi_project.development.panel_records import recent_records
from fastapi_project.panel import generate

from shared.modules.catalog import Catalog
from tests.architecture.test_panel_evidence import check, status


def test_duplicate_calculation_hint_uses_actual_source(tmp_path: Path) -> None:
    code = """def calculate(value):
    first = value * 2
    second = first + 3
    third = second * 4
    fourth = third - 1
    fifth = fourth + 8
    sixth = fifth // 2
    seventh = sixth * 9
    return seventh
"""
    for name in ("sample_first", "sample_second"):
        target = tmp_path / "server/service" / name / "calc/derive.py"
        target.parent.mkdir(parents=True)
        target.write_text(code)
    hints = duplicate_hints(tmp_path)
    assert len(hints) == 1
    assert {item["package"] for item in hints[0]["locations"]} == {"sample_first", "sample_second"}
    target.write_text(code.replace("+ 8", "+ 9"))
    assert not duplicate_hints(tmp_path)


def test_dependency_violation_includes_source_and_target(tmp_path: Path) -> None:
    target = tmp_path / "server/service/sample_first/steps/build.py"
    target.parent.mkdir(parents=True)
    target.write_text("from service.sample_second.calc.derive import calculate\n")
    issues, edges = dependency_issues(tmp_path)
    assert any(
        issue["source"].endswith("steps/build.py") and issue["line"] == 1 for issue in issues
    )
    assert any(
        edge["source"] == "sample_first"
        and edge["target"] == "sample_second"
        and edge["kind"] == "invalid"
        for edge in edges
    )


def test_record_details_export_metadata_only() -> None:
    record = check("synthetic-detail")
    for suite in record["suites"]:
        suite["cases"][0]["durations"] = {"setup": 0.2, "call": 0.5}
        suite["cases"][0]["runs"][0]["secret"] = "raw-business-value"
    details = recent_records("sample_source", status(), [record])
    assert details[0]["scope"] == {"kind": "all"} and details[0]["current_module"]
    assert all(
        suite["counts"]["passed"] == 1 and suite["test_seconds"] == 0.7
        for suite in details[0]["suites"]
    )
    assert "raw-business-value" not in json.dumps(details)


def test_twenty_modules_share_loaded_check_streams(tmp_path: Path, monkeypatch) -> None:
    names = [f"sample_package{number}" for number in range(20)]
    save_check(
        tmp_path,
        {
            "passed": True,
            "source_changed": False,
            "finished_at": datetime.now(UTC).isoformat(),
            "checks": {},
            "fingerprints": dict.fromkeys(names, "same-version"),
            "scope": {"kind": "all"},
            "suites": [
                {
                    "database": database,
                    "exit_code": 0,
                    "cases": [
                        {
                            "nodeid": f"tests/modules/{name}/test_run.py::test_run",
                            "outcome": "passed",
                            "runs": [],
                        }
                        for name in names
                    ],
                }
                for database in ("sqlite", "postgresql")
            ],
        },
    )
    records = read_checks(tmp_path, include_cases=False)
    original = check_storage.iter_cases
    loaded = []

    def counted(suite):
        loaded.append(suite["database"])
        yield from original(suite)

    monkeypatch.setattr(check_storage, "iter_cases", counted)
    for name in names:
        result = module_checks(records, name, "same-version")
        assert result["latest"]["sqlite"]["current"]
    assert loaded == ["sqlite", "postgresql"]


def test_corrupt_evidence_replaces_old_panel(tmp_path: Path) -> None:
    output = tmp_path / "out/panel/index.html"
    output.parent.mkdir(parents=True)
    output.write_text("old-stable-green-evidence")
    source = tmp_path / "server/var/development/checks/broken.json"
    source.parent.mkdir(parents=True)
    source.write_text("{broken")
    with pytest.raises(ValueError):
        generate(tmp_path, Catalog([]))
    assert "old-stable-green-evidence" not in output.read_text()
    assert "证据无法读取" in output.read_text()
