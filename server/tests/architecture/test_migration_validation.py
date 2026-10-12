"""
真实隔离数据库验证两头合并的旧版增量和全新建库，旧行来自独立合成数据。
"""

import os
from pathlib import Path

import pytest
from fastapi_project.development.migration_merge import migration_plan, write_merge
from fastapi_project.development.migration_verify import compare_paths, verify

from tests.architecture.test_migration_merge import revision


# 最小Alembic工程不加载产品配置，迁移地址只从测试命令显式取得。
def project(root: Path) -> None:
    folder = root / "server"
    folder.mkdir()
    (folder / "alembic.ini").write_text("[alembic]\nscript_location = migrations\n")
    migrations = folder / "migrations"
    migrations.mkdir()
    (migrations / "env.py").write_text("""
import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
def run(connection):
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
async def main():
    url = context.get_x_argument(as_dictionary=True)['url']
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(run)
    await engine.dispose()
asyncio.run(main())
""")
    revision(
        root,
        "a0",
        None,
        'op.create_table("seed_rows", sa.Column("id", sa.Integer(), primary_key=True), '
        'sa.Column("value", sa.String()))\n'
        'op.create_index("ix_seed_value", "seed_rows", ["value"], '
        'sqlite_where=sa.text("value IS NOT NULL"), '
        'postgresql_where=sa.text("value IS NOT NULL"))',
    )
    revision(
        root,
        "b1",
        "a0",
        'op.create_table("sample_a", sa.Column("id", sa.Integer(), primary_key=True))',
    )
    revision(
        root,
        "b2",
        "a0",
        'op.create_table("sample_b", sa.Column("id", sa.Integer(), primary_key=True))',
    )
    write_merge(root, migration_plan(root))


# SQLite真实旧行升级后仍在，结构与从零创建完全一致。
@pytest.mark.anyio
async def test_sqlite_incremental_and_fresh_schema(tmp_path: Path) -> None:
    project(tmp_path)
    urls = tuple("sqlite+aiosqlite:///" + str(tmp_path / name) for name in ("old.db", "fresh.db"))
    result = await compare_paths(
        tmp_path,
        urls,
        "a0",
        [{"table": "seed_rows", "values": {"id": 7, "value": "synthetic-old-row"}}],
    )
    assert result["schema_equal"] and result["seed_rows_preserved"] and result["seed_rows"] == 1


# 双库验证明确使用本目标自有PG容器控制连接，凭据只在内存中组装，不存日志。
@pytest.mark.anyio
@pytest.mark.postgres_only
async def test_real_dual_database_incremental_migration(tmp_path: Path) -> None:
    project(tmp_path)
    url = os.environ.get("APP_TEST_CONTROL_URL")
    if not url and os.environ.get("APP_TEST_OWNED_DATABASE") == "1":
        url = os.environ.get("APP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("需要显式隔离PostgreSQL测试控制连接")
    result = await verify(
        tmp_path,
        "a0",
        url,
        [{"table": "seed_rows", "values": {"id": 7, "value": "synthetic-old-row"}}],
    )
    assert result["sqlite"]["schema_equal"] and result["postgresql"]["schema_equal"]
    assert result["postgresql"]["seed_rows_preserved"]
