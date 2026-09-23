"""
测试共用的应用配置：临时数据库、测试用服务密钥、数据库重置。
设置环境变量 APP_TEST_DATABASE_URL 时，全部测试改用这个数据库（例如 PostgreSQL）运行。
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import shared.access.audit
import shared.jobs.tables
import shared.records.tables
from app.setup.catalog import MODULES
from shared.access.keys import ApiKeyConfig, hash_key
from shared.config.settings import Settings
from shared.db.schema import head_revision
from shared.db.tables import metadata

LOADED = (MODULES, shared.jobs.tables, shared.records.tables, shared.access.audit)

KEY = {"X-API-Key": "test-full-key"}
READER = {"X-API-Key": "test-reader-key"}

KEYS = [
    ApiKeyConfig(
        name="tester", key_sha256=hash_key("test-full-key"), permissions=["*"], org_id="*"
    ),
    ApiKeyConfig(
        name="reader",
        key_sha256=hash_key("test-reader-key"),
        permissions=["product_catalog.read", "order_quote.read"],
    ),
]


# 返回测试使用的数据库地址：默认是临时目录中的 SQLite。
def database_url(folder: Path) -> str:
    return os.environ.get("APP_TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{folder}/test.db"


# 判断当前测试是否在 PostgreSQL 上运行。
def on_postgres() -> bool:
    return os.environ.get("APP_TEST_DATABASE_URL", "").startswith("postgresql")


# 生成测试配置，可以覆盖个别配置项。
def make_settings(folder: Path, **changes: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "test",
        "database_url": database_url(folder),
        "api_keys": KEYS,
        "file_root": str(folder / "files"),
        "upload_root": str(folder / "uploads"),
        "docs": True,
        "step_checks": True,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


# 清空并重建全部表，并记下当前迁移版本，使就绪检查通过。
async def reset_database(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.drop_all)
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await connection.run_sync(metadata.create_all)
        await connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await connection.execute(
            text("INSERT INTO alembic_version VALUES (:head)"), {"head": head_revision()}
        )
    await engine.dispose()


# 在同步测试中重置数据库。
def reset_database_now(url: str) -> None:
    asyncio.run(reset_database(url))
