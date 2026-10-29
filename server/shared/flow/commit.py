from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.db.database import Database
from shared.errors.framework import ResultUnknown
from shared.flow.scope import Transaction
from shared.records.models import RunRecord

Hook = Callable[[AsyncConnection, Data, str], Awaitable[None]]


async def commit_writes(
    database: Database, tx: Transaction, run: RunRecord, hook: Hook | None, result: Data
) -> None:
    if tx.connection is None:
        run.writes = "none"
        if hook is not None:
            async with database.write() as connection:
                await hook(connection, result, run.id)
        return
    if hook is not None:
        await hook(tx.connection, result, run.id)
    try:
        await tx.connection.commit()
    except Exception as error:
        run.writes = "unknown"
        raise ResultUnknown(
            f"提交写入时出错（{type(error).__name__}），保存结果尚不能确认"
        ) from error
    run.writes = "committed"
