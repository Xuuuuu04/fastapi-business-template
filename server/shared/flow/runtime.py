"""
执行器 Runtime：接口、后台任务和模块之间的调用都经过这里。
入口调用检查权限，成功结束时提交写入、失败时回滚；模块之间的调用沿用上层的事务和剩余时间。
每次运行都留下运行记录，异常会带上运行编号，方便按编号查询排查信息。
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from opentelemetry import context as otel_context
from opentelemetry import trace

from shared.access.caller import Caller
from shared.data.models import Data
from shared.db.budget import QueryPolicy, merge_child
from shared.db.database import Database
from shared.errors.framework import StepRuleBroken
from shared.flow.auditing import audit_failure, audit_hook
from shared.flow.commit import Hook, commit_writes
from shared.flow.entry_errors import check_access, fill_error, settle_entry, translate
from shared.flow.heavy import HeavySteps
from shared.flow.query_budget import check_query_budget
from shared.flow.runner import execute
from shared.flow.scope import Scope, Transaction
from shared.flow.streaming import stream_events
from shared.jobs.checkpoint import Checkpoint
from shared.jobs.imports import begin_import, reconcile_import
from shared.jobs.submission import submit_entry
from shared.modules.catalog import Binding, Catalog
from shared.modules.contract import Contract
from shared.records.models import RunRecord, StepRecord
from shared.records.opening import open_record
from shared.records.recorder import Recorder
from shared.records.segments import warn_slow_batch
from shared.scenarios.observations import ObservationPosition
from shared.scenarios.simulation import mark_simulated
from shared.timing.clock import Clock, RealClock
from shared.timing.current import clocked

if TYPE_CHECKING:
    from shared.access.vault import Vault
    from shared.cache.backends import Cache
    from shared.effects.service import EffectService
    from shared.files.storage import FileStorage
    from shared.files.uploads import UploadArea
    from shared.flow.inject import JobSubmitter
    from shared.model_calls.service import ModelService
    from shared.remote_calls.service import RemoteService
    from shared.telemetry.service import Telemetry

log = logging.getLogger("server.runtime")

MAX_DEPTH = 8


# 执行已登记的业务操作，管理步骤、事务、模块调用与运行记录。
class Runtime:
    allow_simulation: bool = False

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
        heavy: HeavySteps | None = None,
        query_policy: QueryPolicy | None = None,
        effects: "EffectService | None" = None,
        clock: Clock | None = None,
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
        self.heavy = heavy or HeavySteps()
        self.query_policy = query_policy or QueryPolicy()
        self.effects = effects
        self.clock = clock or RealClock()
        self._started: dict[str, float] = {}

    # 从接口或任务入口执行一个操作：检查权限，结束时提交或回滚写入。
    @clocked
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
        checkpoint: Checkpoint | None = None,
        record_success: bool = True,
        deadline: float | None = None,
        observation_position: ObservationPosition | None = None,
    ) -> Out:
        binding = self.catalog.binding(item)
        if not item.entry:
            raise StepRuleBroken(f"操作 {item.name} 是内部操作，只能由其他模块调用")
        own_deadline = self.clock.monotonic() + item.timeout
        deadline = min(own_deadline, deadline) if deadline is not None else own_deadline
        scope = Scope(self, caller, request_id, job_id, deadline, tx=Transaction(), emitter=emitter)
        scope.checkpoint, scope.record_success = checkpoint, record_success
        scope.observation_position = observation_position
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
            plan = self.catalog.plan(item.name)
            import_plan = plan.import_plan if plan is not None else None
            begin_import(import_plan, scope.checkpoint, run)
            result = await self.clock.run(
                execute(binding, input, scope, run), deadline=scope.deadline
            )
            check_query_budget(self, run, item)
            if scope.checkpoint is not None:
                scope.checkpoint.validate()
                connection = await scope.tx.writer(self.database, "分段提交")
                scope.checkpoint.record(run)
                if import_plan is not None and scope.checkpoint.done:
                    await reconcile_import(connection, import_plan, run.import_report)
            hook = audit_hook(item, scope, before_commit)
            await commit_writes(self.database, scope.tx, run, hook, result)
            if scope.checkpoint is not None:
                scope.checkpoint.record(run, committed=True)
            await self.close_run(run, "ok")
            return result
        except BaseException as error:
            problem = await self.settle(scope, run, error)
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
        loop_time = self.clock.monotonic()
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
            result = await self.clock.run(
                execute(binding, input, scope, run), deadline=scope.deadline
            )
            check_query_budget(self, run, item)
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
            merge_child(parent_run, run)
            mark_simulated(parent_run, parent_step, run)
            if span is not None and token is not None:
                span.set_attribute("run.status", run.status)
                otel_context.detach(token)
                span.end()

    # 在独立的短事务中登记一个后台任务，返回任务编号。
    @clocked
    async def submit(
        self,
        item: Contract[Data, Data],
        input: Data,
        *,
        caller: Caller,
        key: str = "",
        request_id: str = "",
    ) -> str:
        return await submit_entry(self, item, input, caller, key, request_id)

    # 处理入口调用的失败：回滚写入、整理错误、结束运行记录。
    async def settle(self, scope: Scope, run: RunRecord, error: BaseException) -> BaseException:
        return await settle_entry(self, scope, run, error)

    # 创建一条运行记录并交给记录器。
    def open_run(
        self, binding: Binding, scope: Scope, parent: RunRecord | None, step: StepRecord | None
    ) -> RunRecord:
        run = open_record(self, binding, scope, parent, step)
        self._started[run.id] = self.clock.monotonic()
        return run

    # 结束运行记录；记录器出错只写日志，不影响业务结果。
    async def close_run(self, run: RunRecord, status: str) -> None:
        if not run.query_budget:
            check_query_budget(self, run, self.catalog.by_name[run.contract].contract, failed=True)
        run.status = status
        run.ended_at = self.clock.now()
        started = self._started.pop(run.id, self.clock.monotonic())
        run.elapsed_ms = max(0, self.clock.monotonic() - started) * 1000
        warn_slow_batch(run)
        try:
            await self.recorder.finish(run)
        except Exception:
            log.exception("run_record_failed run_id=%s", run.id)
