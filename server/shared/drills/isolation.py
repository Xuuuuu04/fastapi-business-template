"""
演练数据库隔离：SQLite总是新文件，PostgreSQL总是新schema，退出只删除本次创建空间。
"""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


# 不在原有数据库表上drop/create，PostgreSQL不把public加入演练搜索路径。
@asynccontextmanager
async def isolated(folder: Path, postgres: str = "") -> AsyncIterator[str]:
    if not postgres:
        yield "sqlite+aiosqlite:///" + str(folder / "drill.db")
        return
    url = make_url(postgres)
    if url.get_backend_name() != "postgresql":
        raise ValueError("postgres只接受PostgreSQL隔离连接")
    schema = "fastapi_drill_" + secrets.token_hex(8)
    admin = create_async_engine(url)
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        target = url.update_query_dict({"options": f"-csearch_path={schema}"})
        yield target.render_as_string(hide_password=False)
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
