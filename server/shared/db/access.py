"""
store 使用的数据库入口 Db：只能执行语句，不能提交、回滚或关闭连接。
事务由框架按步骤声明安排；没有 saves=True 的步骤拿到只读的 Db，写入会立刻报错。
"""

import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import Executable, RowMapping, Select, TextClause
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import visitors

from shared.access.caller import Caller
from shared.db.org import check_org
from shared.errors.framework import StepRuleBroken
from shared.errors.kinds import BusinessError

READ_WORDS = ("select", "with", "explain", "show", "values")
WRITE_WORDS = ("insert", "update", "delete", "merge")


class Db:
    # 包装框架准备好的连接；place 是使用它的步骤名称，用于报错。
    def __init__(
        self,
        connection: AsyncConnection,
        *,
        read_only: bool,
        place: str,
        caller: Caller | None = None,
    ) -> None:
        self._connection = connection
        self._read_only = read_only
        self._place = place
        self._caller = caller

    # 执行查询并返回全部行，每行可以按列名取值。
    async def all(self, statement: Executable) -> Sequence[RowMapping]:
        self._check(statement)
        result = await self._connection.execute(statement)
        return result.mappings().all()

    # 执行查询并返回第一行，没有结果时返回 None。
    async def first(self, statement: Executable) -> RowMapping | None:
        self._check(statement)
        result = await self._connection.execute(statement)
        return result.mappings().first()

    # 执行语句并返回恰好一行；没有或多于一行时报错，适合 insert ... returning。
    async def one(self, statement: Executable) -> RowMapping:
        self._check(statement)
        result = await self._connection.execute(statement)
        return result.mappings().one()

    # 执行查询并返回第一行第一列的值。
    async def scalar(self, statement: Executable) -> Any:
        self._check(statement)
        return await self._connection.scalar(statement)

    # 执行插入、修改或删除，返回受影响的行数。
    async def change(self, statement: Executable) -> int:
        self._check(statement)
        result = await self._connection.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    # 带条件修改：语句的条件中写上读到的状态或版本，一行都没有改到时报 missing 这个业务错误，
    # 用于“先读后写”时发现数据已被别人改过。
    async def change_or_fail(self, statement: Executable, missing: BusinessError) -> int:
        count = await self.change(statement)
        if count == 0:
            raise missing
        return count

    # 加锁读取第一行：只能在 saves=True 的步骤中使用，读到的行在本次事务结束前不会被别人修改。
    async def first_for_update(self, statement: Select[Any]) -> RowMapping | None:
        if self._read_only:
            raise StepRuleBroken(
                f"步骤「{self._place}」加锁读取需要声明 saves=True，读和写要在同一事务中"
            )
        return await self.first(statement.with_for_update())

    # 在保存点中执行一段写入；失败时只撤销这一段，事务可以继续。
    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        if self._read_only:
            raise StepRuleBroken(f"步骤「{self._place}」没有声明 saves=True，不能写入数据库")
        async with self._connection.begin_nested():
            yield

    # 只读步骤中遇到写入语句时立刻报错。
    def _check(self, statement: Executable) -> None:
        if self._caller is not None:
            if isinstance(statement, TextClause):
                raise StepRuleBroken("业务数据库请使用表声明构造语句，不能直接执行 SQL 文本")
            check_org(statement, self._caller)
        if self._read_only and is_write(statement):
            raise StepRuleBroken(
                f"步骤「{self._place}」没有声明 saves=True，不能写入数据库。"
                "需要写入时，在 @step 中加上 saves=True。"
            )


# 判断一条语句是否会修改数据；查询中带有写入的公共表表达式（WITH ... DELETE）也算写入。
def is_write(statement: Executable) -> bool:
    if isinstance(statement, TextClause):
        words = re.findall(r"[a-z_]+", statement.text.lower())
        if not words or words[0] not in READ_WORDS:
            return True
        return words[0] == "with" and any(word in WRITE_WORDS for word in words)
    return any(getattr(node, "is_dml", False) for node in visitors.iterate(statement))  # type: ignore[arg-type]
