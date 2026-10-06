"""
store 使用的数据库入口 Db：只能执行语句，不能提交、回滚或关闭连接。
事务由框架按步骤声明安排；没有 saves=True 的步骤拿到只读的 Db，写入会立刻报错。
"""

import re
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Executable,
    RowMapping,
    Select,
    Table,
    TextClause,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import ClauseElement, visitors

from shared.access.caller import SYSTEM, Caller
from shared.db.history import history_rows, save_history
from shared.db.org import check_org
from shared.db.owner import check_owner
from shared.db.tracing import query_record
from shared.errors.framework import InvalidInput, StepRuleBroken
from shared.errors.kinds import BusinessError
from shared.records.models import StepRecord

READ_WORDS = ("select", "with", "explain", "show", "values")
WRITE_WORDS = ("insert", "update", "delete", "merge")


# 步骤使用的数据库入口，检查写入权限和组织条件并记录变更。
class Db:
    # 包装框架准备好的连接；place 是使用它的步骤名称，用于报错。
    def __init__(
        self,
        connection: AsyncConnection,
        *,
        read_only: bool,
        place: str,
        caller: Caller | None = None,
        run_id: str = "",
        record: StepRecord | None = None,
        target: str = "database",
    ) -> None:
        self._connection = connection
        self._read_only = read_only
        self._place = place
        self._caller = caller
        self._run_id = run_id
        self._record, self._target = record, target

    # 执行查询并返回全部行，每行可以按列名取值。
    async def all(self, statement: Executable) -> Sequence[RowMapping]:
        with query_record(self._record, statement, "all", self._target) as call:
            self._check(statement)
            rows = (await self._connection.execute(statement)).mappings().all()
            if call is not None:
                call.rows = len(rows)
            return rows

    # 执行查询并返回第一行，没有结果时返回 None。
    async def first(self, statement: Executable) -> RowMapping | None:
        with query_record(self._record, statement, "first", self._target) as call:
            self._check(statement)
            row = (await self._connection.execute(statement)).mappings().first()
            if call is not None:
                call.rows = int(row is not None)
            return row

    # 执行语句并返回恰好一行；没有或多于一行时报错，适合 insert ... returning。
    async def one(self, statement: Executable) -> RowMapping:
        with query_record(self._record, statement, "one", self._target) as call:
            self._check(statement)
            row = (await self._connection.execute(statement)).mappings().one()
            if call is not None:
                call.rows = 1
            return row

    # 执行查询并返回第一行第一列的值。
    async def scalar(self, statement: Executable) -> Any:
        with query_record(self._record, statement, "scalar", self._target):
            self._check(statement)
            return await self._connection.scalar(statement)

    # 执行插入、修改或删除，返回受影响的行数。
    # SQLAlchemy 2.0.28 起默认只保证修改和删除的行数；PostgreSQL 上插入会自动带 RETURNING，
    # 不打开 preserve_rowcount 时行数是 -1。这里统一打开，插入、修改、删除都拿到真实行数。
    async def change(self, statement: Executable) -> int:
        with query_record(self._record, statement, "change", self._target) as call:
            self._check(statement)
            result = await self._connection.execute(
                statement, execution_options={"preserve_rowcount": True}
            )
            count = int(getattr(result, "rowcount", 0) or 0)
            if call is not None:
                call.rows = count if count >= 0 else None
            return count

    # 按位置续读一页：按唯一且可排序的列 key 排序，after 是上一页返回的位置；
    # 数据量大时不必跳过前面的行，越往后也一样快。返回本页的行和下一页的位置（没有下一页为空）。
    async def page_after(
        self, statement: Select[Any], key: ColumnElement[Any], after: str, limit: int
    ) -> tuple[Sequence[RowMapping], str]:
        if after:
            statement = statement.where(key > type_of(key)(after))
        rows = await self.all(statement.order_by(key).limit(limit + 1))
        if len(rows) <= limit:
            return rows, ""
        return rows[:limit], str(rows[limit - 1][key.name])

    # 修改并记录变更历史：先加锁读出要改的记录，修改后把前后不同的字段写进变更历史，与修改同一事务。
    # values 只能是普通值，不能是 SQL 表达式；quiet 中的列（例如修改时间）一起修改但不记历史；
    # key 是记录的主键列名。
    async def update_tracked(
        self,
        table: Table,
        where: ColumnElement[bool],
        values: dict[str, Any],
        *,
        quiet: dict[str, Any] | None = None,
        key: str = "id",
    ) -> int:
        if any(isinstance(value, ClauseElement) for value in values.values()):
            raise StepRuleBroken("update_tracked 的 values 只能是普通值，不能是 SQL 表达式")
        before = await self.all_for_update(select(table).where(where))
        statement = update(table).where(where).values(**values, **(quiet or {}))
        count = await self.change(statement)
        caller = self._caller or SYSTEM
        rows = history_rows(table, key, before, values, caller, self._run_id)
        await save_history(self._connection, rows, self._record, self._target)
        return count

    # 加锁读取全部行：只能在 saves=True 的步骤中使用。
    async def all_for_update(self, statement: Select[Any]) -> Sequence[RowMapping]:
        if self._read_only:
            raise StepRuleBroken(
                f"步骤“{self._place}”加锁读取需要声明 saves=True，读和写要在同一事务中"
            )
        return await self.all(statement.with_for_update())

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
                f"步骤“{self._place}”加锁读取需要声明 saves=True，读和写要在同一事务中"
            )
        return await self.first(statement.with_for_update())

    # 在保存点中执行一段写入；失败时只撤销这一段，事务可以继续。
    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        if self._read_only:
            raise StepRuleBroken(f"步骤“{self._place}”没有声明 saves=True，不能写入数据库")
        async with self._connection.begin_nested():
            yield

    # 只读步骤中遇到写入语句时立刻报错。
    def _check(self, statement: Executable) -> None:
        if self._caller is not None:
            if isinstance(statement, TextClause):
                raise StepRuleBroken("业务数据库请使用表声明构造语句，不能直接执行 SQL 文本")
            check_org(statement, self._caller)
            check_owner(statement, self._caller)
        if self._read_only and is_write(statement):
            raise StepRuleBroken(
                f"步骤“{self._place}”没有声明 saves=True，不能写入数据库。"
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


# 位置文字转回列的 Python 类型，例如整数编号；转不了时报参数错误，不静默当成从头读。
def type_of(key: ColumnElement[Any]) -> Callable[[str], Any]:
    kind = key.type.python_type

    # 转换并在失败时说明原因。
    def convert(text: str) -> Any:
        try:
            return kind(text)
        except ValueError:
            raise InvalidInput(f"after 位置 {text} 格式不对") from None

    return convert
