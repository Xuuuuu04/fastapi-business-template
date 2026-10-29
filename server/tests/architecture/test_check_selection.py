import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi_check.check import INTEGRITY, QUALITY, steps
from fastapi_check.quality.report import Problem, in_modules
from fastapi_project.development.evidence import (
    full_check_current,
    latest_full_check,
    system_fingerprint,
)
from fastapi_project.development.selection import (
    Selection,
    affected_modules,
    module_files,
    module_names,
    previous_graph,
    select_affected,
    validate_modules,
)

from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES


def test_multi_package_plan_runs_common_checks_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = module_names(["sample_accounts,sample_records", "sample_records"])
    assert names == ("sample_accounts", "sample_records")
    monkeypatch.setattr("fastapi_check.check.module_files", lambda names: ["sample.py"])
    plan = steps(Selection(names))
    assert [title for title, _ in plan] == [
        "代码风格",
        "代码格式",
        "类型检查",
        "接口文档",
        "模块测试",
    ]
    command = plan[-1][1]
    assert command.count("tests/modules/sample_records") == 1
    assert "tests/integration/sample_accounts" in command
    assert all(test in command for test in INTEGRITY)
    assert QUALITY in command
    assert plan[0][1] == ["ruff", "check", "sample.py"]
    assert plan[1][1] == ["ruff", "format", "--check", "sample.py"]


def test_module_quality_keeps_only_own_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fastapi_project.development.selection.module_files",
        lambda names: ["app/api/v1/sample_records.py"],
    )
    own = [
        Problem("service/sample_records/steps/build_fee.py", 3, "step_name", "本包"),
        Problem("tests/modules/sample_records/test_fee.py", 9, "comment", "本包"),
        Problem("app/api/v1/sample_records.py", 1, "docstring", "本包接口"),
        Problem("server/service/sample_records/README.md", 4, "writing_style", "本包说明"),
    ]
    others = [
        Problem("service/sample_records_extra/steps/build_fee.py", 3, "step_name", "名字相近"),
        Problem("tests/conftest.py", 1, "comment", "框架文件"),
    ]
    assert in_modules(own + others, ["sample_records"]) == own
    assert in_modules(own + others, []) == own + others


def test_quick_plan_is_local_and_not_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection = Selection(("sample_records",), quick=True)
    monkeypatch.setattr("fastapi_check.check.module_files", lambda names: ["sample.py"])
    plan = steps(selection)
    assert len(plan) == 3
    assert all("mypy" not in command and "docs" not in command for _, command in plan)
    assert not any(test in plan[-1][1] for test in INTEGRITY)
    assert selection.scope() == {"kind": "quick", "modules": ["sample_records"]}
    assert latest_full_check([{"scope": selection.scope()}]) is None


def test_old_and_new_graph_union_keeps_removed_callers() -> None:
    old = {"order": ["stock"], "refund": ["order"], "job": ["stock"]}
    new = {"order": [], "refund": ["order"], "customer": []}
    assert affected_modules(["stock"], [old, new]) == {"stock", "order", "refund", "job"}


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    folder = tmp_path / "repo"
    path = folder / "server/service/sample_records/steps/files.py"
    path.parent.mkdir(parents=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "初始"],
    ):
        subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True)
    return folder


def test_affected_selection_and_unknown_old_caller(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = repository / "server/service/sample_records/steps/files.py"
    path.write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr("fastapi_project.development.selection.previous_graph", lambda *args: {})
    catalog = Catalog(MODULES)
    selected = select_affected(catalog, "HEAD", repository)
    assert selected.modules == ("sample_records",)
    monkeypatch.setattr(
        "fastapi_project.development.selection.previous_graph",
        lambda *args: {"old_caller": ["sample_records"]},
    )
    selected = select_affected(catalog, "HEAD", repository)
    assert selected.modules == () and "已删除" in selected.reasons[0]


@pytest.mark.parametrize("path", ["server/shared/new.py", "unknown.txt"])
def test_affected_shared_or_unknown_changes_require_full(repository: Path, path: str) -> None:
    file = repository / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("content\n", encoding="utf-8")
    selected = select_affected(Catalog(MODULES), "HEAD", repository)
    assert not selected.modules and selected.reasons


def test_unchanged_and_unreadable_graph(repository: Path) -> None:
    catalog = Catalog(MODULES)
    assert select_affected(catalog, "HEAD", repository).unchanged
    (repository / "server/service/sample_records/steps/files.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    selected = select_affected(catalog, "HEAD", repository)
    assert not selected.modules and "无法安全缩小" in selected.reasons[0]
    with pytest.raises(ValueError, match="旧版本依赖"):
        previous_graph(repository, "HEAD")


def test_full_check_tracks_registration_and_exact_modules(tmp_path: Path) -> None:
    file = tmp_path / "server/app/setup/catalog.py"
    file.parent.mkdir(parents=True)
    file.write_text("MODULES = []\n", encoding="utf-8")
    record = {
        "fingerprints": {"a": "1"},
        "source_changed": False,
        "system_fingerprint": system_fingerprint(tmp_path),
    }
    assert full_check_current(record, {"a": "1"}, tmp_path)
    assert not full_check_current(record, {}, tmp_path)
    file.write_text("MODULES = [new]\n", encoding="utf-8")
    assert not full_check_current(record, {"a": "1"}, tmp_path)


@pytest.mark.parametrize(
    "relative",
    [
        "server/shared/probe.py",
        "server/uv.lock",
        "server/tests/framework/test_probe.py",
        ".agents/skills/fastapi-guide/SKILL.md",
        "server/migrations/probe.py",
    ],
)
def test_empty_template_expires_after_framework_change(tmp_path: Path, relative: str) -> None:
    source = tmp_path / relative
    source.parent.mkdir(parents=True)
    source.write_text("first\n")
    record = {
        "fingerprints": {},
        "source_changed": False,
        "system_fingerprint": system_fingerprint(tmp_path),
    }
    assert full_check_current(record, {}, tmp_path)
    source.write_text("second\n")
    assert not full_check_current(record, {}, tmp_path)


def test_validation_and_local_files(tmp_path: Path) -> None:
    catalog = Catalog(MODULES)
    with pytest.raises(ValueError, match="没有登记"):
        validate_modules(("not_registered",), catalog)
    with pytest.raises(ValueError, match="缺少"):
        validate_modules(("sample_records",), catalog, tmp_path)
    from tests.architecture.test_history_versions import sample_project

    sample_project(tmp_path)
    files = module_files(("sample_records",), tmp_path / "server")
    assert "app/api/v1/sample_records.py" in files
    assert not any("sample_accounts" in path for path in files)


def test_product_template_validation_tracks_tool_files_only(tmp_path: Path) -> None:
    from tests.check_profile import template_tools_unchanged

    root = tmp_path / "product"
    tool = root / ".agents/skills/fastapi-check/scripts/fastapi_check/probe.py"
    devtool = root / "server/devtools/src/fastapi_dev/probe.py"
    for path in (tool, devtool):
        path.parent.mkdir(parents=True)
        path.write_text("VALUE = 1\n", encoding="utf-8")
    assert not template_tools_unchanged(root)
    origin = root / "template-source.json"
    origin.write_text(
        json.dumps(
            {
                "files": {
                    path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (tool, devtool)
                },
            }
        ),
        encoding="utf-8",
    )
    assert template_tools_unchanged(root)
    for relative in (
        "server/service/sample/steps.py",
        "server/uv.lock",
        "server/migrations/versions/product.py",
        "server/shared/flow/view.py",
        "server/framework.lock",
        "server/pyproject.toml",
        ".agents/skills/fastapi-check/SKILL.md",
    ):
        changed = root / relative
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text("product change\n", encoding="utf-8")
    assert template_tools_unchanged(root)
    for path in (tool, devtool):
        path.write_text("VALUE = 2\n", encoding="utf-8")
        assert not template_tools_unchanged(root)
        path.write_text("VALUE = 1\n", encoding="utf-8")
    origin.write_text("{", encoding="utf-8")
    assert not template_tools_unchanged(root)


@pytest.mark.parametrize(
    ("group", "delivery", "count"), [("all", "0", 1), ("all", "1", 1), ("framework", "0", 2)]
)
def test_product_template_selection_respects_delivery(
    group: str, delivery: str, count: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi_check.quality.rules import ROOT

    from tests import resources

    monkeypatch.setenv("APP_TEST_GROUP", group)
    monkeypatch.setenv("APP_DEVELOPMENT_DELIVERY", delivery)
    monkeypatch.setattr("tests.check_profile.template_tools_unchanged", lambda root: True)
    items = [
        SimpleNamespace(
            path=ROOT / "tests/architecture" / name, get_closest_marker=lambda name: None
        )
        for name in ("test_tools.py", "test_structure.py")
    ]
    removed = []
    config = SimpleNamespace(
        hook=SimpleNamespace(pytest_deselected=lambda items: removed.extend(items))
    )
    resources.pytest_collection_modifyitems(config, items)
    assert len(items) == count and len(removed) == 2 - count
    assert any(item.path.name == "test_structure.py" for item in items)
