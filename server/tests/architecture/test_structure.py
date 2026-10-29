import ast
import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from fastapi_check.quality.registry import check_registry
from fastapi_check.quality.rules import ROOT
from fastapi_module.new_module import add_module, add_route
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.setup.build import build
from app.setup.catalog import MODULES
from app.setup.web import create_app
from shared.db.tables import metadata
from shared.modules.catalog import Catalog
from shared.modules.validation.imports import check_imports
from tests.testing_app import KEY, database_url, make_settings


def test_import_rules() -> None:
    assert [problem.text() for problem in check_imports()] == []


def test_registry_is_complete() -> None:
    assert [problem.text() for problem in check_registry(Catalog(MODULES))] == []


def test_migrations_match_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = database_url(tmp_path)
    asyncio.run(drop_everything(url))
    monkeypatch.setenv("APP_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(config, "head")
    assert asyncio.run(differences_from(url)) == []


async def drop_everything(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(drop_present_tables)
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()


def drop_present_tables(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        return
    for name in inspect(connection).get_table_names():
        connection.execute(text(f'DROP TABLE "{name}"'))


async def differences_from(url: str) -> list[object]:
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        found = await connection.run_sync(compare)
    await engine.dispose()
    return found


def compare(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return list(compare_metadata(context, metadata))


def test_framework_runs_without_modules(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        assert client.get("/health/live").status_code == 200
        body = client.get("/api/system/modules", headers=KEY).json()
        assert body["modules"] == [] and client.get("/openapi.json").status_code == 200


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
