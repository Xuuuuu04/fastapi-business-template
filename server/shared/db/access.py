import re
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import (
    ColumnElement,
    Executable,
    RowMapping,
    Select,
    Table,
    TextClause,
    func,
    insert,
    literal,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import ClauseElement, visitors

from shared.access.caller import SYSTEM, Caller
from shared.db.explain import attach
from shared.db.history import history_rows, save_history
from shared.db.org import check_org
from shared.db.owner import check_owner
from shared.db.sizing import rows_bytes, value_bytes
from shared.db.tracing import query_record
from shared.errors.framework import InvalidInput, StepRuleBroken
from shared.errors.kinds import BusinessError
from shared.records.models import StepRecord

READ_WORDS = ("select", "with", "explain", "show", "values")
WRITE_WORDS = ("insert", "update", "delete", "merge")


class Db:
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
        org_setting: str = "",
    ) -> None:
        self._connection = connection
        self._read_only = read_only
        self._place = place
        self._caller = caller
        self._run_id = run_id
        self._record, self._target = record, target
        self._org_setting = org_setting

    async def all(self, statement: Executable) -> Sequence[RowMapping]:
        with query_record(self._record, statement, "all", self._target) as call:
            self._check(statement)
            await self._bind_org()
            rows = (await self._connection.execute(statement)).mappings().all()
            if call is not None:
                call.rows = len(rows)
                call.bytes = rows_bytes(rows)
            await attach(self._connection, self._record, statement, call)
            return rows

    async def first(self, statement: Executable) -> RowMapping | None:
        with query_record(self._record, statement, "first", self._target) as call:
            self._check(statement)
            await self._bind_org()
            row = (await self._connection.execute(statement)).mappings().first()
            if call is not None:
                call.rows = int(row is not None)
                call.bytes = rows_bytes([row] if row is not None else [])
            await attach(self._connection, self._record, statement, call)
            return row

    async def one(
        self, statement: Executable, *, conflict: BusinessError | None = None
    ) -> RowMapping:
        with query_record(self._record, statement, "one", self._target) as call:
            self._check(statement)
            await self._bind_org()
            row = (await self._execute(statement, conflict)).mappings().one()
            if call is not None:
                call.rows = 1
                call.bytes = rows_bytes([row])
            await attach(self._connection, self._record, statement, call)
            return row

    async def scalar(self, statement: Executable) -> Any:
        with query_record(self._record, statement, "scalar", self._target) as call:
            self._check(statement)
            await self._bind_org()
            value = await self._connection.scalar(statement)
            if call is not None:
                call.bytes = value_bytes(value)
            await attach(self._connection, self._record, statement, call)
            return value

    async def change(self, statement: Executable, *, conflict: BusinessError | None = None) -> int:
        with query_record(self._record, statement, "change", self._target) as call:
            self._check(statement)
            await self._bind_org()
            result = await self._execute(statement, conflict, {"preserve_rowcount": True})
            count = int(getattr(result, "rowcount", 0) or 0)
            if call is not None:
                call.rows = count if count >= 0 else None
                call.bytes = 0
            return count

    async def insert_many(self, table: Table, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        if not rows[0]:
            raise StepRuleBroken("批量插入必须明确写入字段")
        dialect = self._connection.dialect
        limit = min(
            100,
            dialect.insertmanyvalues_page_size,
            ((dialect.insertmanyvalues_max_parameters or 32700) - 1) // len(table.c),
        )
        if len(rows) > limit or any(row.keys() != rows[0].keys() for row in rows):
            raise StepRuleBroken("批量插入必须使用相同字段，且不超过单条 SQL 参数及100行上限")
        if not dialect.use_insertmanyvalues or not dialect.insert_executemany_returning:
            raise StepRuleBroken("当前数据库不支持一次 SQL 批量插入")
        statement = insert(table).returning(literal(1))
        with query_record(self._record, statement, "change", self._target) as call:
            self._check(insert(table).values(rows))
            await self._bind_org()
            result = await self._connection.execute(statement, rows)
            count = len(result.all())
            if call is not None:
                call.rows, call.bytes = count, 0
            return count

    async def page_after(
        self, statement: Select[Any], key: ColumnElement[Any], after: str, limit: int
    ) -> tuple[Sequence[RowMapping], str]:
        if after:
            statement = statement.where(key > type_of(key)(after))
        rows = await self.all(statement.order_by(key).limit(limit + 1))
        if len(rows) <= limit:
            return rows, ""
        return rows[:limit], str(rows[limit - 1][key.name])

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

    async def all_for_update(self, statement: Select[Any]) -> Sequence[RowMapping]:
        if self._read_only:
            raise StepRuleBroken(
                f"步骤“{self._place}”加锁读取需要声明 saves=True，读和写要在同一事务中"
            )
        return await self.all(statement.with_for_update())

    async def _execute(
        self,
        statement: Executable,
        conflict: BusinessError | None,
        options: dict[str, Any] | None = None,
    ) -> Any:
        try:
            return await self._connection.execute(statement, execution_options=options)
        except IntegrityError as error:
            if conflict is not None and unique_violation(error):
                raise conflict from None
            raise

    async def change_or_fail(self, statement: Executable, missing: BusinessError) -> int:
        count = await self.change(statement)
        if count == 0:
            raise missing
        return count

    async def first_for_update(self, statement: Select[Any]) -> RowMapping | None:
        if self._read_only:
            raise StepRuleBroken(
                f"步骤“{self._place}”加锁读取需要声明 saves=True，读和写要在同一事务中"
            )
        return await self.first(statement.with_for_update())

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        if self._read_only:
            raise StepRuleBroken(f"步骤“{self._place}”没有声明 saves=True，不能写入数据库")
        async with self._connection.begin_nested():
            yield

    async def _bind_org(self) -> None:
        if not self._org_setting or self._connection.dialect.name != "postgresql":
            return
        caller = self._caller
        org = caller.org_id if caller is not None and caller.org_id != "*" else ""
        sync = self._connection.sync_connection
        if sync is None:
            return
        transaction = sync.get_transaction()
        cached = sync.info.get("org_binding")
        if cached == (transaction, self._org_setting, org):
            return
        await self._connection.execute(select(func.set_config(self._org_setting, org, True)))
        sync.info["org_binding"] = (sync.get_transaction(), self._org_setting, org)

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


def is_write(statement: Executable) -> bool:
    if isinstance(statement, TextClause):
        words = re.findall(r"[a-z_]+", statement.text.lower())
        if not words or words[0] not in READ_WORDS:
            return True
        return words[0] == "with" and any(word in WRITE_WORDS for word in words)
    return any(
        getattr(node, "is_dml", False) for node in visitors.iterate(cast(ClauseElement, statement))
    )


def type_of(key: ColumnElement[Any]) -> Callable[[str], Any]:
    kind = key.type.python_type

    def convert(text: str) -> Any:
        try:
            return kind(text)
        except ValueError:
            raise InvalidInput(f"分页游标 {text} 格式无效") from None

    return convert


def unique_violation(error: IntegrityError) -> bool:
    state = getattr(error.orig, "sqlstate", None)
    return state == "23505" or "UNIQUE constraint failed" in str(error.orig)
