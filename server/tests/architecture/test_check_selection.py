"""
分层检查：多包去重、快速范围、旧调用方与未知变化，均用独立输入验证。
"""

import subprocess
from pathlib import Path

import pytest
from fastapi_check.check import INTEGRITY, steps
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


# 本例输入明确要求同一个包只测试一次，不重复四项公共检查。
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
        "生成文档",
        "模块测试",
    ]
    command = plan[-1][1]
    assert command.count("tests/modules/sample_records") == 1
    assert "tests/integration/sample_accounts" in command
    assert all(test in command for test in INTEGRITY)


# 快速检查不包含类型、生成文档或整合测试，记录范围也不能是完整检查。
def test_quick_plan_is_local_and_not_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection = Selection(("sample_records",), quick=True)
    monkeypatch.setattr("fastapi_check.check.module_files", lambda names: ["sample.py"])
    plan = steps(selection)
    assert len(plan) == 3
    assert all(
        "mypy" not in command and "fastapi_docs.export_docs" not in command for _, command in plan
    )
    assert not any(test in plan[-1][1] for test in INTEGRITY)
    assert selection.scope() == {"kind": "quick", "modules": ["sample_records"]}
    assert latest_full_check([{"scope": selection.scope()}]) is None


# 旧依赖即使已经删除，原调用方与传递调用方仍属于受影响范围。
def test_old_and_new_graph_union_keeps_removed_callers() -> None:
    old = {"order": ["stock"], "refund": ["order"], "job": ["stock"]}
    new = {"order": [], "refund": ["order"], "customer": []}
    assert affected_modules(["stock"], [old, new]) == {"stock", "order", "refund", "job"}


# 创建只有业务源码的独立仓库；测试不调用当前项目 Git、不修改工作区。
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


# 修改业务步骤只选择本包；已删除旧调用方不在目录中时改为完整检查。
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


# 公共改动、无法识别的文件与不能读取的历史版本均不缩小检查范围。
@pytest.mark.parametrize("path", ["server/shared/new.py", "unknown.txt"])
def test_affected_shared_or_unknown_changes_require_full(repository: Path, path: str) -> None:
    file = repository / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("content\n", encoding="utf-8")
    selected = select_affected(Catalog(MODULES), "HEAD", repository)
    assert not selected.modules and selected.reasons


# 没有改动保持未执行，历史图读取失败时明确全检查，不伪造成功。
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


# 当前包版本不变也不能沿用登记改变后的完整检查；删除模块也必须过期。
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


# 空模板同样核对完整框架、工具、依赖与测试版本，不能把空模块列表当作当前证据。
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


# 不存在的模块和缺测试目录都明确失败；局部 Ruff 范围包含模块路由。
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
