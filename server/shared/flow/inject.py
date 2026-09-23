"""
按步骤的参数名准备工具：store、call、model、later、caller、note。
每个工具只允许步骤声明过的范围，例如 call 只能调用 uses 中的操作，只读步骤的 store 不能写入。
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.db.access import Db
from shared.errors.framework import StepRuleBroken
from shared.flow.scope import Scope
from shared.flow.step import Step
from shared.model_calls.gate import ModelGate
from shared.modules.contract import Contract
from shared.records.models import RunRecord, StepRecord

MAX_NOTES = 20
MAX_NOTE_TEXT = 200


class JobSubmitter(Protocol):
    # 在给定的写入事务中登记一个后台任务，返回任务编号。
    async def submit(
        self,
        connection: AsyncConnection,
        item: Contract[Any, Any],
        input: Data,
        caller: Caller,
        *,
        key: str,
        request_id: str,
    ) -> str: ...


class Call:
    # 绑定本次运行、步骤记录和步骤声明的可调用操作。
    def __init__(self, scope: Scope, run: RunRecord, record: StepRecord, part: Step) -> None:
        self._scope, self._run, self._record, self._part = scope, run, record, part
        self._busy = False

    # 调用一个声明过的操作，返回它的结果。
    async def __call__[In: Data, Out: Data](self, item: Contract[In, Out], input: In) -> Out:
        if item not in self._part.uses:
            raise StepRuleBroken(
                f"步骤「{self._part.title}」调用了未声明的操作 {item.name}，请在 uses 中声明"
            )
        if self._busy:
            raise StepRuleBroken(f"步骤「{self._part.title}」中的模块调用要逐个 await，不能并发")
        self._busy = True
        try:
            return await self._scope.runtime.call(item, input, self._scope, self._run, self._record)
        finally:
            self._busy = False


class Later:
    # 绑定本次运行的写入事务和步骤声明的可登记任务。
    def __init__(self, scope: Scope, record: StepRecord, part: Step) -> None:
        self._scope, self._record, self._part = scope, record, part

    # 登记一个后台任务，与本次写入同一事务提交；返回任务编号。
    async def __call__(self, item: Contract[Any, Any], input: Data, *, key: str = "") -> str:
        runtime = self._scope.runtime
        if item not in self._part.later:
            raise StepRuleBroken(
                f"步骤「{self._part.title}」登记了未声明的任务 {item.name}，请在 later 中声明"
            )
        if runtime.jobs is None:
            raise StepRuleBroken("没有启用后台任务功能")
        connection = await self._scope.tx.writer(runtime.database, self._part.title)
        job_id = await runtime.jobs.submit(
            connection, item, input, self._scope.caller, key=key, request_id=self._scope.request_id
        )
        self._record.notes.append(f"登记任务「{item.title}」，编号 {job_id}")
        return job_id


class NoteWriter:
    # 绑定要写入说明的步骤记录。
    def __init__(self, record: StepRecord) -> None:
        self._record = record

    # 写下一条数据说明，例如“排除 3 条记录：缺少单价”。
    def __call__(self, text: str) -> None:
        if len(self._record.notes) < MAX_NOTES:
            self._record.notes.append(text[:MAX_NOTE_TEXT])


# 按步骤参数准备工具，步骤结束后释放只读连接。
@asynccontextmanager
async def tools_for(
    part: Step, scope: Scope, run: RunRecord, record: StepRecord, store: Any
) -> AsyncIterator[dict[str, Any]]:
    tools: dict[str, Any] = {}
    params = set(part.params)
    async with AsyncExitStack() as stack:
        if "store" in params:
            connection = await store_connection(part, scope, stack)
            tools["store"] = store(Db(connection, read_only=not part.saves, place=part.title))
        if "call" in params:
            tools["call"] = Call(scope, run, record, part)
        if "model" in params:
            tools["model"] = ModelGate(
                scope.runtime.models, part.prompts, record.models, part.title
            )
        if "later" in params:
            tools["later"] = Later(scope, record, part)
        if "caller" in params:
            tools["caller"] = scope.caller
        if "note" in params:
            tools["note"] = NoteWriter(record)
        yield tools


# 保存步骤使用写入事务；读取步骤在事务开始前用只读连接，之后沿用事务连接以读到本次写入。
async def store_connection(part: Step, scope: Scope, stack: AsyncExitStack) -> AsyncConnection:
    database = scope.runtime.database
    if part.saves:
        return await scope.tx.writer(database, part.title)
    if scope.tx.connection is not None:
        return scope.tx.connection
    return await stack.enter_async_context(database.read())
