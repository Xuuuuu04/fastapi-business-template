"""
测试夹具：配置、HTTP 客户端、组装好的服务。每个测试使用重置过的数据库，不读取项目的 .env。
SQLite 上自动跳过标记 postgres_only 的测试。
完整运行默认测试（不带路径和筛选参数）时，检查模块总目录中的每个操作至少被执行过一次。
"""

import asyncio
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
from tests.framework.sample_modules import calc_module, outer_module, sample_metadata
from tests.framework.sample_routes import sample_router
from tests.testing_app import make_settings, on_postgres, reset_database, reset_database_now

EXECUTED: set[str] = set()


# 记下测试期间实际执行过的操作。
@pytest.fixture(autouse=True, scope="session")
def track_operations() -> Iterator[None]:
    original = Runtime.open_run

    # 在创建运行记录时记下操作名。
    def tracked(self: Runtime, binding: Any, scope: Any, parent: Any, step: Any) -> Any:
        EXECUTED.add(binding.contract.name)
        return original(self, binding, scope, parent, step)

    Runtime.open_run = tracked  # type: ignore[method-assign]
    yield
    Runtime.open_run = original  # type: ignore[method-assign]


# 完整运行时，模块总目录中没有被任何测试执行过的操作会让测试失败。
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    partial = [arg for arg in config.invocation_params.args if not str(arg).startswith("-")]
    if exitstatus != 0 or partial or config.option.keyword or config.option.markexpr:
        return
    registered = {item.name for module in MODULES for item in module.provides}
    missing = sorted(registered - EXECUTED)
    if missing:
        reporter = config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"以下操作在测试中一次也没有执行，请补测试：{', '.join(missing)}", red=True
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


# 在 SQLite 上跳过只对 PostgreSQL 有意义的测试。
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if on_postgres():
        return
    skip = pytest.mark.skip(reason="只在 PostgreSQL 上运行，设置 APP_TEST_DATABASE_URL 后执行")
    for item in items:
        if "postgres_only" in item.keywords:
            item.add_marker(skip)


# 异步测试使用 asyncio。
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# 每个测试一份独立配置。
@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


# 从真实的应用工厂启动，返回 HTTP 客户端。
@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    reset_database_now(settings.database_url)
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


# 组装好的服务（使用模拟大模型），用于直接调用执行器的测试。
@pytest.fixture
async def services(settings: Settings) -> AsyncIterator[Services]:
    await reset_database(settings.database_url)
    built = build(settings, provider=FakeModel())
    try:
        yield built
    finally:
        await built.close()


# 模拟大模型：把提示词中的文字原样带回，方便检查变量是否填对。
def echo(request: ModelRequest) -> str:
    return f"说明：{request.user}"


# 用框架测试的示例模块组装的服务，并建好示例表。
@pytest.fixture
async def sample(settings: Settings) -> AsyncIterator[Services]:
    await reset_database(settings.database_url)
    built = build(
        settings, modules=[calc_module, outer_module], provider=FakeModel({"describe_mark": echo})
    )
    await create_sample_tables(built)
    try:
        yield built
    finally:
        await built.close()


# 建好示例模块使用的表。
async def create_sample_tables(services: Services) -> None:
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)


# 只启用示例模块的应用，系统接口和安全测试使用它，不依赖可删除的示例业务。
@pytest.fixture
def sample_client(settings: Settings) -> Iterator[TestClient]:
    reset_database_now(settings.database_url)
    modules = [calc_module, outer_module]
    built = build(settings, modules=modules, provider=FakeModel({"describe_mark": echo}))
    asyncio.run(create_sample_tables(built))
    app = create_app(settings, built)
    app.include_router(sample_router)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
