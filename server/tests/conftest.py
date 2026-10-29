import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.setup.build import Services, build
from app.setup.catalog import MODULES
from app.setup.web import create_app
from shared.config.settings import Settings
from shared.flow.runtime import Runtime
from shared.model_calls.providers import FakeModel, ModelRequest
from shared.records.version import source_version
from tests.framework.sample_modules import calc_module, outer_module, sample_metadata
from tests.framework.sample_routes import sample_router
from tests.scheduling import schedule
from tests.testing_app import (
    make_settings,
    on_postgres,
    prepare_test_database,
    prepare_test_database_now,
)

pytest_plugins = ["tests.failure_reports", "tests.development_history", "tests.resources"]

EXECUTED: set[str] = set()


@pytest.fixture(autouse=True, scope="session")
def track_operations() -> Iterator[None]:
    original = Runtime.open_run

    def tracked(self: Runtime, binding: Any, scope: Any, parent: Any, step: Any) -> Any:
        EXECUTED.add(binding.contract.name)
        return original(self, binding, scope, parent, step)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Runtime, "open_run", tracked)
        yield


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if hasattr(session.config, "workerinput"):
        session.config.workeroutput["executed_operations"] = sorted(EXECUTED)
        return
    config = session.config
    partial = [
        arg
        for arg in config.invocation_params.args
        if not str(arg).startswith("-") and (Path(str(arg)).exists() or "::" in str(arg))
    ]
    selected = json.loads(os.environ.get("APP_DEVELOPMENT_MODULES", "[]"))
    if (
        exitstatus != 0
        or config.option.keyword
        or config.option.markexpr
        or os.environ.get("APP_TEST_GROUP", "all") != "all"
        or (partial and not selected)
    ):
        return
    registered = {
        item.name
        for module in MODULES
        if not selected or module.name in selected
        for item in module.provides
    }
    missing = sorted(registered - EXECUTED)
    if missing:
        reporter = config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"以下操作在测试中一次也没有执行，请补测试：{', '.join(missing)}", red=True
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: Any) -> None:
    EXECUTED.update(node.workeroutput.get("executed_operations", []))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    schedule(items)
    if os.environ.get("APP_DEVELOPMENT_REPEAT_DATABASE") == "1":
        once = pytest.mark.skip(
            reason="此模板测试固定使用 SQLite，已在本轮默认检查成功执行，不在第二数据库重复"
        )
        for item in items:
            if "sqlite_template" in item.keywords:
                item.add_marker(once)
    if on_postgres():
        return
    skip = pytest.mark.skip(reason="只在 PostgreSQL 上运行，设置 APP_TEST_DATABASE_URL 后执行")
    for item in items:
        if "postgres_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    prepare_test_database_now(settings.database_url)
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
async def services(settings: Settings) -> AsyncIterator[Services]:
    await prepare_test_database(settings.database_url)
    built = build(settings, provider=FakeModel())
    try:
        yield built
    finally:
        await built.close()


def echo(request: ModelRequest) -> str:
    return f"说明：{request.user}"


@pytest.fixture
async def sample(settings: Settings) -> AsyncIterator[Services]:
    await prepare_test_database(settings.database_url)
    built = build(
        settings, modules=[calc_module, outer_module], provider=FakeModel({"describe_mark": echo})
    )
    built.runtime.source_version = source_version(Path(__file__).resolve().parents[1])
    await create_sample_tables(built)
    try:
        yield built
    finally:
        await built.close()


async def create_sample_tables(services: Services) -> None:
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)


@pytest.fixture
def sample_client(settings: Settings) -> Iterator[TestClient]:
    prepare_test_database_now(settings.database_url)
    modules = [calc_module, outer_module]
    built = build(settings, modules=modules, provider=FakeModel({"describe_mark": echo}))
    built.runtime.source_version = source_version(Path(__file__).resolve().parents[1])
    asyncio.run(create_sample_tables(built))
    app = create_app(settings, built)
    app.include_router(sample_router)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
