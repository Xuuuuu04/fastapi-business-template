"""
每轮和每个测试进程使用独立资源；PostgreSQL只创建和删除带本轮所有权标记的新数据库。
"""

import asyncio
import os
import secrets
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi_project.development.database_leases import (
    DatabaseLease,
    allocate_database,
    control_dsn,
    release_database,
)

__all__ = ["DatabaseLease", "allocate_database", "control_dsn", "release_database"]


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
    from tests.check_profile import template_tool, template_tools_unchanged

    selected = os.environ.get("APP_TEST_GROUP", "all")
    root = Path(__file__).resolve().parents[2]
    # 模板工具测试断言的是空模板本身，只在模板仓库运行；产品里模板工具未改动时交付也省略。
    product = selected != "framework" and template_tools_unchanged(root)
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
