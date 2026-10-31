from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi_check.quality.registry import check_registry
from fastapi_module import editing, new_operation

from shared.modules.catalog import Catalog
from tests.framework.sample_modules import calc_module, explain
from tests.resources import pytest_collection_modifyitems


def operation_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "service/order_desk"
    folder.mkdir(parents=True)
    files = {
        "module.json": "{}",
        "public.py": "__all__ = []",
        "data.py": "",
        "flow.py": "",
        "module.py": "module = Module(provides={})",
    }
    for name, text in files.items():
        (folder / name).write_text(text)
    monkeypatch.setattr(new_operation, "ROOT", tmp_path)
    monkeypatch.setattr(editing, "ROOT", tmp_path)
    return folder


@pytest.mark.parametrize("relative", ["calc/normalize_text.py", "steps/build_normalize_text.py"])
def test_operation_generation_preserves_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    folder = operation_root(tmp_path, monkeypatch)
    target = folder / relative
    target.parent.mkdir()
    target.write_text("EXISTING = 1")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="新文件已存在"):
        new_operation.changes("order_desk", "normalize_text", "整理文本")
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_generated_route_includes_contract_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_root(tmp_path, monkeypatch)
    route = tmp_path / "app/api/v1/order_desk.py"
    route.parent.mkdir(parents=True)
    route.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")
    text = new_operation.changes("order_desk", "normalize_text", "整理文本", http=True)[route]
    compile(text, str(route), "exec")
    assert "responses=responses_for(order_desk.normalize_text)" in text


def test_registry_requires_full_registered_operation_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "fastapi_check.quality.registry.local_routes", lambda root: {"other.explain": []}
    )
    problems = check_registry(Catalog([calc_module]), tmp_path)
    assert any(p.rule == "not_exposed" and explain.name in p.message for p in problems)


def test_group_filter_always_keeps_quality_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_TEST_GROUP", "module")
    item = SimpleNamespace(
        path="tests/quality/test_project_quality.py", get_closest_marker=lambda _: None
    )
    dropped = []
    config = SimpleNamespace(
        hook=SimpleNamespace(pytest_deselected=lambda **kw: dropped.extend(kw["items"]))
    )
    selected = [item]
    pytest_collection_modifyitems(config, selected)
    assert selected == [item] and not dropped
