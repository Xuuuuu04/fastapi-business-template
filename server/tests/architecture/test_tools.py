import json
from pathlib import Path

from fastapi_docs.openapi import openapi_text
from fastapi_migration.compare_api import compare

from shared.modules.validation.framework_lock import differences, digests

COPY_FLAG = "TEMPLATE_COPY_RUN"


def test_compare_api() -> None:
    before = {
        "paths": {"/a": {"get": {"summary": "甲"}}, "/b": {"post": {"summary": "乙"}}},
        "components": {"schemas": {"A": {"type": "object"}, "B": {"type": "object"}}},
    }
    after = {
        "paths": {"/a": {"get": {"summary": "甲改"}}, "/c": {"get": {"summary": "丙"}}},
        "components": {"schemas": {"A": {"type": "string"}}},
    }
    assert compare(before, after) == [
        "删除接口：POST /b",
        "新增接口：GET /c",
        "接口声明变化：GET /a",
        "删除数据模型：B",
        "数据模型变化：A",
    ]
    assert compare(before, before) == []


def test_openapi_text() -> None:
    assert "/health/live" in json.loads(openapi_text())["paths"]


def test_framework_lock(tmp_path: Path) -> None:
    assert "还没有 framework.lock" in differences(tmp_path)[0]
    folder = tmp_path / "shared"
    folder.mkdir()
    (folder / "a.py").write_text("A = 1\n", encoding="utf-8")
    (folder / "b.py").write_text("B = 1\n", encoding="utf-8")
    (tmp_path / "framework.lock").write_text(json.dumps(digests(tmp_path)), encoding="utf-8")
    assert differences(tmp_path) == []
    (folder / "a.py").write_text("A = 2\n", encoding="utf-8")
    (folder / "b.py").unlink()
    (folder / "c.py").write_text("C = 1\n", encoding="utf-8")
    assert differences(tmp_path) == ["新增：shared/c.py", "删除：shared/b.py", "修改：shared/a.py"]


def test_framework_lock_pyproject(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\ndependencies = ["redis>=7,<8"]\n\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    (tmp_path / "framework.lock").write_text(json.dumps(digests(tmp_path)), encoding="utf-8")
    project.write_text(
        '[project]\ndependencies = ["redis>=8,<9"]\n\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    assert differences(tmp_path) == []
    project.write_text(
        '[project]\ndependencies = ["redis>=8,<9"]\n\n[tool.ruff]\nline-length = 200\n',
        encoding="utf-8",
    )
    assert differences(tmp_path) == ["修改：pyproject.toml"]
