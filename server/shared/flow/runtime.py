"""
执行器 Runtime：接口、后台任务和模块之间的调用都经过这里。
入口调用检查权限，成功结束时提交写入、失败时回滚；模块之间的调用沿用上层的事务和剩余时间。
每次运行都留下运行记录，异常会带上运行编号，方便按编号查询排查信息。
"""

import asyncio
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from opentelemetry import context as otel_context
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.db.database import Database
from shared.errors.framework import NotAllowed, NotSignedIn, ResultUnknown, StepRuleBroken
from shared.flow.auditing import audit_failure, audit_hook
from shared.flow.entry_errors import check_access, fill_error, translate
from shared.flow.runner import execute
from shared.flow.scope import Scope, Transaction
from shared.flow.streaming import stream_events
from shared.modules.catalog import Binding, Catalog
from shared.modules.contract import Contract
from shared.records.models import RunRecord, StepRecord
from shared.records.recorder import Recorder

if TYPE_CHECKING:
    from shared.access.vault import Vault
    from shared.cache.backends import Cache
    from shared.files.storage import FileStorage
    from shared.files.uploads import UploadArea
    from shared.flow.inject import JobSubmitter
    from shared.model_calls.service import ModelService
    from shared.remote_calls.service import RemoteService
    from shared.telemetry.service import Telemetry

log = logging.getLogger("server.runtime")

Hook = Callable[[AsyncConnection, Data, str], Awaitable[None]]
MAX_DEPTH = 8


# 执行已登记的业务操作，管理步骤、事务、模块调用与运行记录。
class Runtime:
    # 汇总执行所需的模块目录、数据库、记录器、大模型服务和任务登记入口。
    def __init__(
        self,
        catalog: Catalog,
        database: Database,
        recorder: Recorder,
        *,
        models: "ModelService | None" = None,
        jobs: "JobSubmitter | None" = None,
        remotes: "RemoteService | None" = None,
        cache: "Cache | None" = None,
        files: "FileStorage | None" = None,
        uploads: "UploadArea | None" = None,
        legacy: "Database | None" = None,
        telemetry: "Telemetry | None" = None,
        vault: "Vault | None" = None,
        code_version: str = "dev",
        step_checks: bool = True,
    ) -> None:
        self.catalog = catalog
        self.database = database
        self.recorder = recorder
        self.models = models
        self.jobs = jobs
        self.remotes = remotes
        self.cache = cache
        self.files = files
        self.uploads = uploads
        self.legacy = legacy
        self.telemetry = telemetry
        self.vault = vault
        self.code_version = code_version
        self.source_version = ""
        self.step_checks = step_checks

    # 从接口或任务入口执行一个操作：检查权限，结束时提交或回滚写入。
    async def run[In: Data, Out: Data](
        self,
        item: Contract[In, Out],
        input: In,
        *,
        caller: Caller,
        request_id: str = "",
        job_id: str = "",
        before_commit: Hook | None = None,
        on_start: Callable[[str], None] | None = None,
        emitter: Callable[[str], Awaitable[None]] | None = None,
    ) -> Out:
        binding = self.catalog.binding(item)
        if not item.entry:
            raise StepRuleBroken(f"操作 {item.name} 是内部操作，只能由其他模块调用")
        deadline = asyncio.get_running_loop().time() + item.timeout
        scope = Scope(self, caller, request_id, job_id, deadline, tx=Transaction(), emitter=emitter)
        run = self.open_run(binding, scope, None, None)
        span = (
            self.telemetry.tracer.start_span(
                "run", attributes={"run.id": run.id, "operation": item.name}
            )
            if self.telemetry is not None
            else None
        )
        token = otel_context.attach(trace.set_span_in_context(span)) if span else None
        scope.root_id = run.id
        if on_start is not None:
            on_start(run.id)
        try:
            return cast(
                Out, await self.execute_entry(binding, item, input, scope, run, before_commit)
            )
        finally:
            try:
                await scope.tx.close()
            finally:
                if span is not None and token is not None:
                    span.set_attribute("run.status", run.status)
                    otel_context.detach(token)
                    span.end()

    # 执行入口并在同一事务中写成功操作记录；失败时回滚并单独写失败操作记录。
    async def execute_entry(
        self,
        binding: Binding,
        item: Contract[Any, Any],
        input: Data,
        scope: Scope,
        run: RunRecord,
        before_commit: Hook | None,
    ) -> Data:
        try:
            check_access(item, scope.caller)
            async with asyncio.timeout_at(scope.deadline):
                result = await execute(binding, input, scope, run)
            hook = audit_hook(item, scope, before_commit)
            await self.commit(scope.tx, run, hook, result)
            await self.close_run(run, "ok")
            return result
        except BaseException as error:
            problem = await self.settle(scope.tx, run, error)
            await audit_failure(self.database, item, scope, run, problem)
            if problem is error:
                raise
            raise problem from error

    # 把声明为 stream 的操作变成 SSE；客户端断开时取消后台执行并等待回滚。
    async def stream[In: Data, Out: Data](
        self, item: Contract[In, Out], input: In, *, caller: Caller, request_id: str = ""
    ) -> AsyncIterator[bytes]:
        async for event in stream_events(self, item, input, caller=caller, request_id=request_id):
            yield event

    # 执行模块之间的调用：沿用上层事务和剩余时间，记录为下一层运行。
    async def call[In: Data, Out: Data](
        self,
        item: Contract[In, Out],
        input: In,
        parent: Scope,
        parent_run: RunRecord,
        parent_step: StepRecord,
    ) -> Out:
        binding = self.catalog.binding(item)
        if parent.depth + 1 > MAX_DEPTH:
            raise StepRuleBroken(f"模块调用超过 {MAX_DEPTH} 层，请检查调用关系")
        loop_time = asyncio.get_running_loop().time()
        scope = replace(
            parent, depth=parent.depth + 1, deadline=min(parent.deadline, loop_time + item.timeout)
        )
        run = self.open_run(binding, scope, parent_run, parent_step)
        span = (
            self.telemetry.tracer.start_span(
                "module_call", attributes={"run.id": run.id, "operation": item.name}
            )
            if self.telemetry is not None
            else None
        )
        token = otel_context.attach(trace.set_span_in_context(span)) if span else None
        parent_step.children.append(run.id)
        try:
            async with asyncio.timeout_at(scope.deadline):
                result = await execute(binding, input, scope, run)
        except BaseException as error:
            problem = translate(error)
            fill_error(run, problem)
            run.writes = "in_parent" if scope.tx.connection else "none"
            await self.close_run(run, "failed")
            if problem is error:
                raise
            raise problem from error
        else:
            run.writes = "in_parent" if scope.tx.connection else "none"
            await self.close_run(run, "ok")
            return cast(Out, result)
        finally:
            if span is not None and token is not None:
                span.set_attribute("run.status", run.status)
                otel_context.detach(token)
                span.end()

    # 在独立的短事务中登记一个后台任务，返回任务编号。
    async def submit(
        self,
        item: Contract[Data, Data],
        input: Data,
        *,
        caller: Caller,
        key: str = "",
        request_id: str = "",
    ) -> str:
        if self.jobs is None:
            raise StepRuleBroken("没有启用后台任务功能")
        check_access(item, caller)
        async with self.database.write() as connection:
            return await self.jobs.submit(
                connection, item, input, caller, key=key, request_id=request_id
            )

    # 提交写入；hook 与业务写入同一事务执行，没有业务写入时单独开一个短事务。
    # 提交本身出错时无法确认是否已保存，报告“结果待确认”。
    async def commit(
        self, tx: Transaction, run: RunRecord, hook: Hook | None, result: Data
    ) -> None:
        if tx.connection is None:
            run.writes = "none"
            if hook is not None:
                async with self.database.write() as connection:
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

    # 处理入口调用的失败：回滚写入、整理错误、结束运行记录。
    async def settle(self, tx: Transaction, run: RunRecord, error: BaseException) -> BaseException:
        problem = translate(error)
        if run.writes != "unknown":
            run.writes = await tx.rollback()
        fill_error(run, problem)
        refused = isinstance(problem, NotAllowed | NotSignedIn) and not run.steps
        status = "refused" if refused else "failed"
        await self.close_run(run, status)
        with suppress(AttributeError):
            problem.run_id = run.id  # type: ignore[attr-defined]
        return problem

    # 创建一条运行记录并交给记录器。
    def open_run(
        self, binding: Binding, scope: Scope, parent: RunRecord | None, step: StepRecord | None
    ) -> RunRecord:
        run_id = secrets.token_hex(8)
        run = RunRecord(
            id=run_id,
            root_id=parent.root_id if parent else run_id,
            parent_id=parent.id if parent else "",
            parent_step=step.id if step else "",
            contract=binding.contract.name,
            title=binding.contract.title,
            module=binding.module.name,
            module_version=binding.module.version,
            code_version=self.code_version,
            source_version=self.source_version,
            request_id=scope.request_id,
            job_id=scope.job_id,
            caller=f"{scope.caller.kind}:{scope.caller.id}",
            started_at=time.time(),
            planned=[part.name for part in binding.flow.steps],
        )
        self.recorder.start(run)
        return run

    # 结束运行记录；记录器出错只写日志，不影响业务结果。
    async def close_run(self, run: RunRecord, status: str) -> None:
        run.status = status
        run.ended_at = time.time()
        run.elapsed_ms = (run.ended_at - run.started_at) * 1000
        try:
            await self.recorder.finish(run)
        except Exception:
            log.exception("run_record_failed run_id=%s", run.id)
