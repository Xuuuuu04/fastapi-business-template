"""
管理数据库连接池、只读连接和写入事务。
只读连接在数据库层面禁止写入：PostgreSQL 用只读事务，SQLite 用 query_only。
业务代码拿不到本文件的对象，只能通过 store 收到的 Db 访问数据库。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


# 管理数据库连接和事务，供接口、后台任务及存储实现共同使用。
class Database:
    # 按连接地址创建连接池；SQLite 额外设置外键、并发等待和事务方式。
    def __init__(
        self, url: str, *, pool_size: int = 10, wait_seconds: float = 10, org_setting: str = ""
    ) -> None:
        self.url = url
        self.org_setting = org_setting
        self.is_sqlite = url.startswith("sqlite")
        self.engine: AsyncEngine = create_async_engine(
            url, **engine_options(url, pool_size, wait_seconds)
        )
        if self.is_sqlite:
            prepare_sqlite(self.engine, wait_seconds)

    # 打开一个只读连接，用完后自动归还。
    @asynccontextmanager
    async def read(self) -> AsyncIterator[AsyncConnection]:
        async with self.engine.connect() as connection:
            if self.is_sqlite:
                await connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            try:
                yield connection
            finally:
                await connection.rollback()
                if self.is_sqlite:
                    await connection.exec_driver_sql("PRAGMA query_only = OFF")
                    await connection.rollback()

    # 打开一个写入事务连接；由调用方负责提交或回滚并关闭。
    async def open_write(self) -> AsyncConnection:
        connection = await self.engine.connect()
        try:
            await connection.begin()
        except BaseException:
            await connection.close()
            raise
        return connection

    # 在一个短事务中执行写入，成功后提交；用于框架自己的表。
    @asynccontextmanager
    async def write(self) -> AsyncIterator[AsyncConnection]:
        async with self.engine.connect() as connection:
            if self.is_sqlite:
                await connection.execution_options(sqlite_writer=True)
            async with connection.begin():
                yield connection

    # 检查数据库能否连通。
    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")

    # 关闭连接池。
    async def close(self) -> None:
        await self.engine.dispose()


# 根据数据库种类整理连接池参数。
def engine_options(url: str, pool_size: int, wait_seconds: float) -> dict[str, Any]:
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return {"connect_args": {"timeout": wait_seconds}}
    return {
        "pool_size": pool_size,
        "max_overflow": 0,
        "pool_timeout": wait_seconds,
        "pool_pre_ping": True,
    }


# 给 SQLite 连接设置外键检查、等待时间，并改由 SQLAlchemy 明确开始事务。
def prepare_sqlite(engine: AsyncEngine, wait_seconds: float) -> None:
    # 每个新连接建立时设置一次。
    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(connection: Any, record: Any) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {int(wait_seconds * 1000)}")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    # 每次开始事务时发出 BEGIN，保证事务范围与代码一致。
    @event.listens_for(engine.sync_engine, "begin")
    def on_begin(connection: Any) -> None:
        statement = (
            "BEGIN IMMEDIATE"
            if connection.get_execution_options().get("sqlite_writer")
            else "BEGIN"
        )
        connection.exec_driver_sql(statement)


# 判断异常是否属于数据库暂时不可用，例如断连、连接池等待超时。
def is_unavailable(error: BaseException) -> bool:
    if isinstance(error, PoolTimeout | InterfaceError):
        return True
    if isinstance(error, OperationalError):
        return not is_readonly_violation(error)
    return isinstance(error, DBAPIError) and error.connection_invalidated


# 判断异常是否因为在只读连接中写入。
def is_readonly_violation(error: BaseException) -> bool:
    text = str(error).lower()
    return "readonly" in text or "read-only" in text or "read only" in text
