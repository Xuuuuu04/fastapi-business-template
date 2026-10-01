"""
架构测试：依赖方向、模块登记与接线、迁移与表定义一致、框架文件摘要、关闭全部业务模块后框架仍能启动、
新模块命令能在当前的登记文件中登记。
"""

import ast
import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.setup.build import build
from app.setup.catalog import MODULES
from app.setup.web import create_app
from shared.db.tables import metadata
from shared.modules.catalog import Catalog
from tests.framework.sample_modules import sample_metadata
from tests.testing_app import KEY, database_url, make_settings
from tools.framework_lock import differences
from tools.new_module import add_module, add_route
from tools.quality.imports import check_imports
from tools.quality.registry import check_registry
from tools.quality.rules import ROOT


# 依赖方向符合规则：业务只用 shared.public 和其他模块的 public.py。
def test_import_rules() -> None:
    assert [problem.text() for problem in check_imports()] == []


# 每个模块都已登记，对外操作接到了接口或任务上，内部操作都被调用。
def test_registry_is_complete() -> None:
    assert [problem.text() for problem in check_registry(Catalog(MODULES))] == []


# 迁移到最新版本后，数据库结构与代码中的表定义一致。
def test_migrations_match_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = database_url(tmp_path)
    asyncio.run(drop_everything(url))
    monkeypatch.setenv("APP_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(config, "head")
    assert asyncio.run(differences_from(url)) == []


# 删除全部表，包括迁移版本表和框架测试的示例表。
async def drop_everything(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(metadata.drop_all)
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()


# 对比数据库结构和代码中的表定义。
async def differences_from(url: str) -> list[object]:
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        found = await connection.run_sync(compare)
    await engine.dispose()
    return found


# 在同步连接上对比结构。
def compare(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return list(compare_metadata(context, metadata))


# 框架文件与 framework.lock 中记录的摘要一致。
def test_framework_files_unchanged() -> None:
    changes = differences()
    assert changes == [], (
        "框架文件有改动，审查后运行 tools.framework_lock --update：\n" + "\n".join(changes)
    )


# 不启用任何业务模块时，框架仍能启动、通过健康检查并提供诊断接口。
def test_framework_runs_without_modules(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        assert client.get("/health/live").status_code == 200
        body = client.get("/api/system/modules", headers=KEY).json()
        assert body["modules"] == [] and client.get("/openapi.json").status_code == 200


# 新模块命令按当前文件格式登记：模块进入清单，接口按模块名分组。
def test_scaffold_registers_in_current_files() -> None:
    changes = (
        (ROOT / "app" / "setup" / "catalog.py", add_module, "sample_new"),
        (ROOT / "app" / "api" / "routers.py", add_route, "sample_new.router"),
    )
    for path, change, item in changes:
        tree = ast.parse(change(path.read_text(encoding="utf-8"), "sample_new"))
        imported = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "sample_new" in imported, path.name
        if path.name == "catalog.py":
            listed = [
                ast.unparse(element)
                for node in tree.body
                if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.List)
                for element in node.value.elts
            ]
            assert listed[-1] == item
        else:
            grouped = next(
                node.value
                for node in tree.body
                if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Dict)
            )
            assert ast.literal_eval(grouped.keys[-1]) == "sample_new"
            assert ast.unparse(grouped.values[-1]) == "(sample_new.router,)"
