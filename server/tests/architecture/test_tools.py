"""
项目工具：接口变化比较、中文接口清单、框架文件摘要，以及新项目的完整起步路径
（删除示例、生成新模块、生成迁移后，副本中的全部测试通过）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.api_doc import api_markdown, docs_app
from tools.compare_api import compare
from tools.framework_lock import differences, digests
from tools.quality.rules import PROJECT
from tools.template.initialization import initialize

COPY_FLAG = "TEMPLATE_COPY_RUN"


# 接口和数据模型的增加、删除、声明变化都被列出；完全相同时没有变化。
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


# 中文接口清单来自实际路由，不需要启动服务和数据库。
def test_api_markdown() -> None:
    schema, text = api_markdown(docs_app())
    assert "/health/live" in schema["paths"]
    assert "接口清单" in text and "/health/live" in text


# 框架文件新增、删除、修改都能被发现；没有摘要文件时提示先生成。
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


# pyproject.toml 只锁定检查配置：改依赖版本不算框架改动，放宽检查规则会被发现。
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


# 新项目的起步路径：删除示例、生成新模块、升级并生成迁移、导出文档后，副本中的全部测试通过。
def test_new_project_path(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("已经在项目副本中运行，不再复制")
    copy = tmp_path / "project"
    initialize(PROJECT, copy, "客户联系样例")
    env = {name: value for name, value in os.environ.items() if not name.startswith("APP_")}
    env |= {COPY_FLAG: "1", "APP_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/copy.db"}
    steps = [
        ["tools.new_module", "customer_contact", "--title", "客户联系人"],
        ["alembic", "upgrade", "head"],
        ["alembic", "revision", "--autogenerate", "-m", "add customer_contact tables"],
        ["tools.export_docs"],
        ["ruff", "format", "--quiet", "migrations"],
        ["tools.check", "--module", "customer_contact"],
        ["pytest", "-q", "-p", "no:cacheprovider"],
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
