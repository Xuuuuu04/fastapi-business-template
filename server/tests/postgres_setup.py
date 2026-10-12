"""
本轮独立PostgreSQL库的结构复用；特殊DDL、权限与迁移测试继续完整重建。
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.db.schema import head_revision
from tests.environment import subprocess_environment

PREPARED: dict[str, str] = {}


# 只有资源插件创建的数据库可以使用快速清理，外部显式连接保持完整重建。
def reusable(url: str, hooks: bool) -> bool:
    return bool(
        url.startswith("postgresql")
        and os.environ.get("APP_TEST_OWNED_DATABASE") == "1"
        and os.environ.get("APP_TEST_REBUILD") != "1"
        and not hooks
    )


# 本worker的结构已经准备好才清数据；版本、表和索引变化会先重新建结构。
async def prepare(url: str, key: str, reset: Any) -> None:
    if PREPARED.get(url) != key:
        if url in PREPARED:
            await reset(url)
        else:
            await asyncio.to_thread(migrate_baseline, url)
        PREPARED[url] = key
        return
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            names = (
                (
                    await connection.execute(
                        text(
                            "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() "
                            "AND tablename <> 'alembic_version' ORDER BY tablename"
                        )
                    )
                )
                .scalars()
                .all()
            )
            if names:
                quote = connection.dialect.identifier_preparer.quote
                await connection.execute(
                    text(
                        "TRUNCATE " + ",".join(quote(name) for name in names) + " RESTART IDENTITY"
                    )
                )
            await connection.execute(text("DELETE FROM alembic_version"))
            await connection.execute(
                text("INSERT INTO alembic_version VALUES (:head)"), {"head": head_revision()}
            )
    finally:
        await engine.dispose()


# 第一次使用实际迁移建立结构；控制连接、生产变量与模型配置不进入子进程。
def migrate_baseline(url: str) -> None:
    environment = subprocess_environment()
    environment.update(APP_ENV="test", APP_DATABASE_URL=url)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", "url=" + url, "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("本轮隔离数据库迁移失败：" + result.stderr[-1500:])
