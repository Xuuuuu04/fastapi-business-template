"""
迁移验证只使用新建的隔离数据库；旧版增量与全新建库比较结构，可插入独立合成旧行。
"""

import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi_check.matrix import clean_environment
from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.database_leases import allocate_database, release_database
from sqlalchemy import MetaData, Table, insert, inspect, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine


# Alembic通过显式测试地址执行，原控制库地址不传入迁移进程。
def upgrade(project: Path, url: str, revision: str) -> None:
    env = clean_environment() | {"APP_ENV": "test", "APP_DATABASE_URL": url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", "url=" + url, "upgrade", revision],
        cwd=project / "server",
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        raise ValueError(
            "隔离迁移执行失败，请核对迁移源码和数据库结构；返回码" + str(result.returncode)
        )


# 结构包括列、索引、主键、外键和唯一约束；不读取生产连接或实际业务数据。
def schema(connection: Any) -> dict:
    inspector = inspect(connection)
    result = {}
    names = [
        (namespace, name)
        for namespace in inspector.get_schema_names()
        if namespace not in {"information_schema", "pg_catalog", "temp"}
        and not namespace.startswith("pg_")
        for name in inspector.get_table_names(schema=namespace)
        if name != "alembic_version"
    ]
    for namespace, name in sorted(names):
        result[namespace + "." + name] = {
            "columns": [
                {key: str(column.get(key)) for key in ("name", "type", "nullable", "default")}
                for column in inspector.get_columns(name, schema=namespace)
            ],
            "indexes": sorted(
                inspector.get_indexes(name, schema=namespace),
                key=lambda item: str(item.get("name")),
            ),
            "primary_key": inspector.get_pk_constraint(name, schema=namespace),
            "foreign_keys": sorted(
                inspector.get_foreign_keys(name, schema=namespace),
                key=lambda item: str(item.get("name")),
            ),
            "unique": sorted(
                inspector.get_unique_constraints(name, schema=namespace),
                key=lambda item: str(item.get("name")),
            ),
            "checks": sorted(
                inspector.get_check_constraints(name, schema=namespace),
                key=lambda item: str(item.get("name")),
            ),
        }
    return json.loads(json.dumps(result, default=str, sort_keys=True))


# 反射回调明确绑定本次表名，异步循环不捕获后来变化的行变量。
def reflected(connection: Connection, name: str) -> Table:
    return Table(name, MetaData(), autoload_with=connection)


# 旧行由独立测试提供，表和列通过实际反射检查，SQL值使用绑定参数。
async def seed(url: str, rows: list[dict]) -> list[dict]:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            tables: dict[str, Table] = {}
            for row in rows:
                name = row["table"]
                if name not in tables:
                    tables[name] = await connection.run_sync(reflected, name)
                if not set(row["values"]) <= set(tables[name].columns.keys()):
                    raise ValueError("合成旧行包含未知列")
                await connection.execute(insert(tables[name]).values(**row["values"]))
        return rows
    finally:
        await engine.dispose()


# 增量升级后检查合成旧行的原字段，结构比较另行检查所有新增列。
async def preserved(url: str, rows: list[dict]) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            for row in rows:
                table = await connection.run_sync(reflected, row["table"])
                query = select(table).where(
                    *(table.c[name] == value for name, value in row["values"].items())
                )
                if (await connection.execute(query)).first() is None:
                    return False
        return True
    finally:
        await engine.dispose()


# 同库类型两条真实迁移路径比较，异常不得被成功结构快照掩盖。
async def compare_paths(
    project: Path, urls: tuple[str, str], anchor: str, rows: list[dict]
) -> dict:
    incremental, fresh = urls
    await asyncio.to_thread(upgrade, project, incremental, anchor)
    await seed(incremental, rows)
    await asyncio.to_thread(upgrade, project, incremental, "head")
    await asyncio.to_thread(upgrade, project, fresh, "head")
    structures = []
    for url in urls:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                structures.append(await connection.run_sync(schema))
        finally:
            await engine.dispose()
    equal = structures[0] == structures[1]
    retained = await preserved(incremental, rows)
    if not equal or not retained:
        diagnostic = {
            "incremental": structures[0],
            "fresh": structures[1],
            "seed_rows_preserved": retained,
        }
        atomic_bytes(
            project / ".agents/records/migration-structure-diff.json",
            json.dumps(diagnostic, default=str, ensure_ascii=False, indent=2).encode(),
        )
        raise ValueError("增量结构与全新建库不一致，或合成旧行未保留")
    digest = hashlib.sha256(
        json.dumps(structures[0], default=str, sort_keys=True).encode()
    ).hexdigest()
    return {
        "schema_equal": equal,
        "seed_rows_preserved": retained,
        "seed_rows": len(rows),
        "schema_digest": digest,
    }


# PostgreSQL只借新资源，始终按所有权标记归还，不在调用方控制库运行upgrade。
async def postgres_paths(project: Path, control: str, anchor: str, rows: list[dict]) -> dict:
    leases: list[Any] = []
    try:
        for worker in ("migration_old", "migration_fresh"):
            leases.append(await allocate_database(control, uuid.uuid4().hex, worker))
        return await compare_paths(project, (leases[0].url, leases[1].url), anchor, rows)
    finally:
        errors = []
        for lease in reversed(leases):
            try:
                await release_database(lease)
            except Exception as error:
                errors.append(type(error).__name__)
        if errors:
            raise ValueError("隔离数据库归还失败：" + ",".join(errors))


# 两类数据库都需要明确执行证据，不用SQLite成功补成PostgreSQL成功。
async def verify(project: Path, anchor: str, postgres: str, rows: list[dict] | None = None) -> dict:
    rows = rows or []
    if len(rows) > 100 or not anchor:
        raise ValueError("迁移验证需要旧版本和不超过100份独立合成行")
    if not postgres:
        raise ValueError("完整迁移验证需要显式PostgreSQL控制连接")
    with tempfile.TemporaryDirectory(prefix="migration-validation-") as folder:
        urls = tuple(
            "sqlite+aiosqlite:///" + str(Path(folder) / name) for name in ("old.db", "fresh.db")
        )
        sqlite = await compare_paths(project, (urls[0], urls[1]), anchor, rows)
    pg = await postgres_paths(project, postgres, anchor, rows)
    return {
        "anchor": anchor,
        "sqlite": sqlite,
        "postgresql": pg,
        "meaning": "隔离合成升级证明，未读取或迁移产品生产数据库",
    }
