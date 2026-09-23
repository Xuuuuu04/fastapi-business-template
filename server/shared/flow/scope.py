"""
一次运行的范围 Scope 和共用的写入事务 Transaction。
最外层操作创建 Scope；它调用的其他操作沿用同一个事务、调用者和剩余时间，只增加调用层数。
事务在第一个 saves=True 的步骤开始，由最外层操作提交或回滚。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.db.database import Database

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime


@dataclass
class Transaction:
    connection: AsyncConnection | None = None
    started_by: str = ""

    # 取得写入事务连接；第一次使用时开始事务，并记下是哪个步骤开始的。
    async def writer(self, database: Database, place: str) -> AsyncConnection:
        if self.connection is None:
            self.connection = await database.open_write()
            self.started_by = place
        return self.connection

    # 撤销尚未提交的写入；返回运行记录中的写入状态。
    async def rollback(self) -> str:
        if self.connection is None:
            return "none"
        try:
            await self.connection.rollback()
        except Exception:
            return "unknown"
        return "rolled_back"

    # 归还连接；未提交的写入会被数据库撤销。
    async def close(self) -> None:
        if self.connection is not None:
            connection, self.connection = self.connection, None
            await connection.close()


@dataclass
class Scope:
    runtime: "Runtime"
    caller: Caller
    request_id: str
    job_id: str
    deadline: float
    depth: int = 0
    root_id: str = ""
    tx: Transaction = field(default_factory=Transaction)
