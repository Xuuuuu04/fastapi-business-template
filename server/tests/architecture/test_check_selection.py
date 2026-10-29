import subprocess
from pathlib import Path

import pytest
from fastapi_check.check import INTEGRITY, QUALITY, steps
from fastapi_check.quality.report import Problem, in_modules
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
    assert QUALITY in plan[-1][1]
    assert selection.scope() == {"kind": "quick", "modules": ["sample_records"]}


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


def test_validation_and_local_files(tmp_path: Path) -> None:
    catalog = Catalog(MODULES)
    with pytest.raises(ValueError, match="没有登记"):
        validate_modules(("not_registered",), catalog)
    with pytest.raises(ValueError, match="缺少"):
        validate_modules(("sample_records",), catalog, tmp_path)
    routers = tmp_path / "server/app/api/routers.py"
    routers.parent.mkdir(parents=True)
    routers.write_text(
        "from app.api.v1 import sample_accounts, sample_records\n\n"
        "MODULE_ROUTERS: dict[str, tuple] = {\n"
        '    "sample_accounts": (sample_accounts.router,),\n'
        '    "sample_records": (sample_records.router,),\n'
        "}\n"
    )
    for name in ("sample_accounts", "sample_records"):
        for relative in (f"service/{name}/module.py", f"app/api/v1/{name}.py"):
            path = tmp_path / "server" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = 1\n")
    files = module_files(("sample_records",), tmp_path / "server")
    assert "app/api/v1/sample_records.py" in files
    assert not any("sample_accounts" in path for path in files)
