"""
按步骤的参数名准备 store、call、model、remote、cache、emit、later、caller、note。
每个工具只允许步骤声明过的范围，例如 call 只能调用 uses 中的操作，只读步骤的 store 不能写入。
"""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.cache.gate import ModuleCache
from shared.data.models import Data
from shared.db.access import Db
from shared.errors.framework import StepRuleBroken
from shared.files.gate import ModuleFiles
from shared.flow.scope import Scope
from shared.flow.step import Step
from shared.jobs.checkpoint import Checkpoint
from shared.model_calls.gate import ModelGate
from shared.modules.contract import Contract
from shared.modules.module import Module
from shared.pipelines.gate import PipelineGate
from shared.records.models import RunRecord, StepRecord
from shared.remote_calls.gate import RemoteGate

MAX_NOTES = 20
MAX_NOTE_TEXT = 200


# 业务步骤登记后台任务时需要的操作约定。
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


# 在步骤内调用已声明的其他模块操作，共享本次执行身份与事务。
class Call:
    # 绑定本次运行、步骤记录和步骤声明的可调用操作。
    def __init__(self, scope: Scope, run: RunRecord, record: StepRecord, part: Step) -> None:
        self._scope, self._run, self._record, self._part = scope, run, record, part
        self._busy = False

    # 调用一个声明过的操作，返回它的结果。
    async def __call__[In: Data, Out: Data](self, item: Contract[In, Out], input: In) -> Out:
        if item not in self._part.uses:
            raise StepRuleBroken(
                f"步骤“{self._part.title}”调用了未声明的操作 {item.name}，请在 uses 中声明"
            )
        if self._busy:
            raise StepRuleBroken(f"步骤“{self._part.title}”中的模块调用要逐个 await，不能并发")
        self._busy = True
        try:
            return await self._scope.runtime.call(item, input, self._scope, self._run, self._record)
        finally:
            self._busy = False


# 在步骤内登记已声明的后台任务，随当前事务一起保存。
class Later:
    # 绑定本次运行的写入事务和步骤声明的可登记任务。
    def __init__(self, scope: Scope, record: StepRecord, part: Step) -> None:
        self._scope, self._record, self._part = scope, record, part

    # 登记一个后台任务，与本次写入同一事务提交；返回任务编号。
    async def __call__(self, item: Contract[Any, Any], input: Data, *, key: str = "") -> str:
        runtime = self._scope.runtime
        if item not in self._part.later:
            raise StepRuleBroken(
                f"步骤“{self._part.title}”登记了未声明的任务 {item.name}，请在 later 中声明"
            )
        if runtime.jobs is None:
            raise StepRuleBroken("没有启用后台任务功能")
        connection = await self._scope.tx.writer(runtime.database, self._part.title)
        job_id = await runtime.jobs.submit(
            connection, item, input, self._scope.caller, key=key, request_id=self._scope.request_id
        )
        self._record.notes.append(f"登记任务“{item.title}”，编号 {job_id}")
        return job_id


# 把必要的数据说明写入当前步骤记录，方便排查业务结果。
class NoteWriter:
    # 绑定要写入说明的步骤记录。
    def __init__(self, record: StepRecord) -> None:
        self._record = record

    # 写下一条数据说明，例如“排除 3 条记录：缺少单价”。
    def __call__(self, text: str) -> None:
        if len(self._record.notes) < MAX_NOTES:
            self._record.notes.append(text[:MAX_NOTE_TEXT])


# 将步骤生成的流式消息发送给接口，同时检查允许发送的格式。
class Emitter:
    # 把一段文本交给流式响应；等待消费方接收，避免无限积压。
    def __init__(self, scope: Scope, record: StepRecord) -> None:
        self._scope, self._record = scope, record

    # 每段最多 64 KiB；客户端断开后上层任务取消并回滚事务。
    async def __call__(self, text: str) -> None:
        if self._scope.emitter is None:
            raise StepRuleBroken("这个操作没有以流式接口执行")
        if len(text.encode("utf-8")) > 64 * 1024:
            raise StepRuleBroken("流式输出的单段文字超过 64 KiB")
        await self._scope.emitter(text)
        self._record.emitted += 1


# 按步骤参数准备工具，步骤结束后释放只读连接。
@asynccontextmanager
async def tools_for(
    part: Step, scope: Scope, run: RunRecord, record: StepRecord, module: Module
) -> AsyncIterator[dict[str, Any]]:
    params = set(part.params)
    async with AsyncExitStack() as stack:
        tools = simple_tools(part, scope, run, record, module, params)
        if "store" in params:
            tools["store"] = await build_store(part, scope, record, module, stack)
        yield tools


# 准备不需要打开连接的工具，只准备步骤参数中出现的。
def simple_tools(
    part: Step, scope: Scope, run: RunRecord, record: StepRecord, module: Module, params: set[str]
) -> dict[str, Any]:
    makers: dict[str, Callable[[], Any]] = {
        "call": lambda: Call(scope, run, record, part),
        "model": lambda: ModelGate(scope.runtime.models, part.prompts, record.models, part.title),
        "remote": lambda: remote_gate(part, scope, record, part.remotes),
        "cache": lambda: module_cache(scope, module.name, record),
        "later": lambda: Later(scope, record, part),
        "caller": lambda: scope.caller,
        "note": lambda: NoteWriter(record),
        "emit": lambda: Emitter(scope, record),
        "checkpoint": lambda: batch_checkpoint(scope),
        "pipeline": lambda: PipelineGate(scope, run, saves=part.saves),
    }
    return {name: make() for name, make in makers.items() if name in params}


# 只有显式分段的后台任务可取得恢复位置，HTTP与普通任务不能借此改变事务。
def batch_checkpoint(scope: Scope) -> Checkpoint:
    if scope.checkpoint is None:
        raise StepRuleBroken("checkpoint 只能用于 JobPlan(segmented=True) 的后台任务")
    return scope.checkpoint


# 按构造参数名准备存储实现所需的依赖；旧库始终使用独立的只读连接。
async def build_store(
    part: Step, scope: Scope, record: StepRecord, module: Module, stack: AsyncExitStack
) -> object:
    factory = module.store
    if factory is None:
        raise StepRuleBroken(f"模块 {module.name} 没有存储实现")
    available: dict[str, Any] = {
        "caller": scope.caller,
        "remote": remote_gate(part, scope, record, module.remotes),
        "cache": module_cache(scope, module.name, record),
    }
    if scope.runtime.vault is not None:
        available["vault"] = scope.runtime.vault
    if scope.runtime.files is not None and scope.runtime.uploads is not None:
        available["files"] = ModuleFiles(scope.runtime.files, scope.runtime.uploads, module.name)
    names = set(inspect.signature(factory).parameters)
    if "db" in names:
        connection = await store_connection(part, scope, stack)
        available["db"] = Db(
            connection,
            read_only=not part.saves,
            place=part.title,
            caller=scope.caller,
            run_id=scope.root_id,
            org_setting=scope.runtime.database.org_setting,
            record=record,
        )
    if "legacy" in names:
        if scope.runtime.legacy is None:
            raise StepRuleBroken("旧系统数据库没有配置 APP_LEGACY_DATABASE_URL")
        old = await stack.enter_async_context(scope.runtime.legacy.read())
        available["legacy"] = Db(
            old, read_only=True, place="旧系统只读库", record=record, target="legacy"
        )
    missing = names - set(available)
    if missing:
        raise StepRuleBroken(f"存储实现 {factory.__name__} 有不认识的构造参数 {sorted(missing)}")
    return factory(**{name: available[name] for name in names})


# 限制外部系统在写入事务开始后调用，并记录请求概要。
def remote_gate(
    part: Step, scope: Scope, record: StepRecord, allowed: tuple[Any, ...]
) -> RemoteGate:
    return RemoteGate(
        scope.runtime.remotes,
        allowed,
        record.remotes,
        part.title,
        lambda: scope.tx.connection is not None,
        scope.remote_writes,
        scope.checkpoint.before_write if scope.checkpoint is not None else None,
        part.endpoints,
        getattr(scope.runtime.remotes, "strict_endpoints", False),
    )


# 缓存键按模块隔离，记录当前步骤的命中和未命中次数。
def module_cache(scope: Scope, name: str, record: StepRecord) -> ModuleCache:
    cache = scope.runtime.cache
    if cache is None:
        raise StepRuleBroken("没有启用缓存")
    return ModuleCache(cache, name, record)


# 保存步骤使用写入事务；读取步骤在事务开始前用只读连接，之后沿用事务连接以读到本次写入。
async def store_connection(part: Step, scope: Scope, stack: AsyncExitStack) -> AsyncConnection:
    database = scope.runtime.database
    if part.saves:
        return await scope.tx.writer(database, part.title)
    if scope.tx.connection is not None:
        return scope.tx.connection
    return await stack.enter_async_context(database.read())
