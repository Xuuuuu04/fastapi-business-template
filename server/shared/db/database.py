from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


class Database:
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

    async def open_write(self) -> AsyncConnection:
        connection = await self.engine.connect()
        try:
            if self.is_sqlite:
                await connection.execution_options(sqlite_writer=True)
            await connection.begin()
        except BaseException:
            await connection.close()
            raise
        return connection

    @asynccontextmanager
    async def write(self) -> AsyncIterator[AsyncConnection]:
        connection = await self.open_write()
        try:
            yield connection
        except BaseException:
            await connection.rollback()
            raise
        else:
            await connection.commit()
        finally:
            await connection.close()

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")

    async def close(self) -> None:
        await self.engine.dispose()


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


def prepare_sqlite(engine: AsyncEngine, wait_seconds: float) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(connection: Any, record: Any) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {int(wait_seconds * 1000)}")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def on_begin(connection: Any) -> None:
        statement = (
            "BEGIN IMMEDIATE"
            if connection.get_execution_options().get("sqlite_writer")
            else "BEGIN"
        )
        connection.exec_driver_sql(statement)


def is_unavailable(error: BaseException) -> bool:
    if isinstance(error, PoolTimeout | InterfaceError):
        return True
    if isinstance(error, OperationalError):
        return not is_readonly_violation(error)
    return isinstance(error, DBAPIError) and error.connection_invalidated


def is_readonly_violation(error: BaseException) -> bool:
    text = str(error).lower()
    return "readonly" in text or "read-only" in text or "read only" in text
