"""
隔离PostgreSQL资源的所有权与归还，开发迁移验证和测试插件共用，不清空控制库。
"""

import secrets
from dataclasses import dataclass

import psycopg
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
    async with await psycopg.AsyncConnection.connect(
        control_dsn(control), autocommit=True, connect_timeout=10
    ) as conn:
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
        control_dsn(lease.control), autocommit=True, connect_timeout=10
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
