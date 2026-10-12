"""
每轮和每个测试进程使用独立资源；PostgreSQL只创建和删除带本轮所有权标记的新数据库。
"""

import asyncio
import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url


# 所有权信息保存在数据库注释和测试配置对象，不依赖当前进程后来改变的环境。
@dataclass(frozen=True)
class DatabaseLease:
    control: str
    name: str
    marker: str
    url: str


# 驱动名称只用于SQLAlchemy；控制连接使用psycopg的标准DSN。
def control_dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


# 新数据库名称与本轮和worker绑定，不清空调用方提供的控制数据库。
async def allocate_database(control: str, run: str, worker: str) -> DatabaseLease:
    suffix = secrets.token_hex(6)
    name = f"fastapi_test_{suffix}_{worker}"
    marker = f"fastapi-tests:{run}:{worker}:{suffix}"
    async with await psycopg.AsyncConnection.connect(control_dsn(control), autocommit=True) as conn:
        await conn.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(name)))
        await conn.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(name),
                sql.Literal(marker),
            )
        )
    url = make_url(control).set(database=name).render_as_string(hide_password=False)
    return DatabaseLease(control, name, marker, url)


# 即使环境被测试改动，也只删除本轮实际创建且标记吻合的数据库。
async def release_database(lease: DatabaseLease) -> None:
    async with await psycopg.AsyncConnection.connect(
        control_dsn(lease.control), autocommit=True
    ) as conn:
        cursor = await conn.execute(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=%s",
            (lease.name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return
        if row[0] != lease.marker or not lease.name.startswith("fastapi_test_"):
            raise RuntimeError("测试数据库所有权不一致，不删除")
        await conn.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(lease.name))
        )


# 控制进程不占数据库，worker或串行进程各持有一份独立数据库。
@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    for key in list(os.environ):
        if any(
            word in key.upper() for word in ("API_KEY", "ACCESS_TOKEN", "CLIENT_SECRET")
        ) and not key.startswith("APP_TEST_"):
            os.environ.pop(key)
    if hasattr(config, "workerinput"):
        worker = config.workerinput["workerid"]
        run = config.workerinput.get("testrunuid", secrets.token_hex(8))
    else:
        worker, run = "master", os.environ.get("APP_TEST_RUN_ID", secrets.token_hex(8))
    config._gen3_resource_root = Path(tempfile.mkdtemp(prefix=f"gen3-{run[:8]}-{worker}-"))
    config._gen3_lease = None
    os.environ["APP_TEST_RESOURCE_PREFIX"] = f"{run}:{worker}:"
    control = os.environ.get("APP_TEST_CONTROL_URL") or os.environ.get("APP_TEST_DATABASE_URL", "")
    if not control.startswith("postgresql"):
        control = ""
    parallel_controller = not hasattr(config, "workerinput") and getattr(
        config.option, "numprocesses", 0
    )
    if control and not parallel_controller:
        try:
            lease = asyncio.run(allocate_database(control, run, worker))
        except Exception as error:
            raise pytest.UsageError(f"无法创建本轮隔离数据库：{type(error).__name__}") from None
        config._gen3_lease = lease
        os.environ["APP_TEST_DATABASE_URL"] = lease.url
        os.environ["APP_TEST_OWNED_DATABASE"] = "1"


# fixture与连接全部结束之后归还数据库，清理失败不得被报告成测试成功。
def pytest_unconfigure(config: pytest.Config) -> None:
    lease = getattr(config, "_gen3_lease", None)
    if lease:
        asyncio.run(release_database(lease))
    root = getattr(config, "_gen3_resource_root", None)
    if root:
        shutil.rmtree(root)


# 分组来自目录或显式标记，未知的测试目录归框架验证，不静默省略。
def test_group(path: Path) -> str:
    parts = path.parts
    if "modules" in parts:
        return "pure" if path.name.startswith("test_calc") else "module"
    if "unit" in parts:
        return "pure"
    if "integration" in parts or "flows" in parts:
        return "flow"
    return "framework"


# 特殊数据库行为显式重建，普通业务测试才复用结构。
def pytest_runtest_setup(item: pytest.Item) -> None:
    special = item.get_closest_marker("database_rebuild") is not None
    os.environ["APP_TEST_REBUILD"] = "1" if special else "0"


# 当前选中的分组和产品角色均写进记录；模板始终运行全部框架验证。
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    from tests.check_profile import product_framework_unchanged, template_tool

    selected = os.environ.get("APP_TEST_GROUP", "all")
    root = Path(__file__).resolve().parents[2]
    product = selected != "framework" and product_framework_unchanged(root)
    kept, deselected = [], []
    for item in items:
        marker = item.get_closest_marker("test_group")
        group = marker.args[0] if marker else test_group(Path(str(item.path)))
        include = (selected == "all" or group == selected) and not (
            product and template_tool(Path(str(item.path)), root)
        )
        (kept if include else deselected).append(item)
    config.hook.pytest_deselected(items=deselected)
    items[:] = kept
