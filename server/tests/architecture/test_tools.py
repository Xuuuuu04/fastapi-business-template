import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_docs.openapi import openapi_text
from fastapi_migration.compare_api import compare

from shared.modules.validation.framework_lock import differences, digests
from tests.environment import subprocess_environment
from tests.template_project import initialize

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


@pytest.mark.sqlite_template
def test_new_project_path(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("已经在项目副本中运行，不再复制")
    copy = tmp_path / "project"
    initialize(PROJECT, copy, "客户联系样例")
    env = subprocess_environment()
    env |= {
        COPY_FLAG: "1",
        "APP_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/copy.db",
        "APP_TEST_WORKERS": "2",
    }
    steps = [
        ["fastapi_dev.main", "new-module", "customer_contact", "--title", "客户联系人"],
        ["alembic", "upgrade", "head"],
        ["alembic", "revision", "--autogenerate", "-m", "add customer_contact tables"],
        ["ruff", "format", "--quiet", "migrations"],
        ["fastapi_dev.main", "docs"],
        ["fastapi_dev.main", "check", "--module", "customer_contact", "--workers", "0"],
        ["pytest", "-q", "-p", "no:cacheprovider", "--dist=load", "--maxschedchunk=2", "-n", "2"],
    ]
    for step in steps:
        done = subprocess.run(
            [sys.executable, "-m", *step],
            cwd=copy / "server",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, (
            f"{' '.join(step)}\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
        )
    schema = json.loads((copy / "doc/api/openapi.json").read_text(encoding="utf-8"))
    assert schema["info"]["title"] == "客户联系样例"
