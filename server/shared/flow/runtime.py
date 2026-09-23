"""
执行器 Runtime：接口、后台任务和模块之间的调用都经过这里。
入口调用检查权限，成功结束时提交写入、失败时回滚；模块之间的调用沿用上层的事务和剩余时间。
每次运行都留下运行记录，异常会带上运行编号，方便按编号查询诊断信息。
"""

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.db.database import Database, is_readonly_violation, is_unavailable
from shared.errors.framework import (
    DatabaseUnavailable,
    NotAllowed,
    NotSignedIn,
    ResultUnknown,
    RunTimeout,
    StepRuleBroken,
)
from shared.errors.kinds import BusinessError
from shared.flow.runner import execute
from shared.flow.scope import Scope, Transaction
from shared.modules.catalog import Binding, Catalog
from shared.modules.contract import Contract
from shared.records.models import RunRecord, StepRecord
from shared.records.recorder import Recorder

if TYPE_CHECKING:
    from shared.flow.inject import JobSubmitter
    from shared.model_calls.service import ModelService

log = logging.getLogger("server.runtime")

Hook = Callable[[AsyncConnection, Data, str], Awaitable[None]]
MAX_DEPTH = 8


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
        code_version: str = "dev",
        step_checks: bool = True,
    ) -> None:
        self.catalog = catalog
        self.database = database
        self.recorder = recorder
        self.models = models
        self.jobs = jobs
        self.code_version = code_version
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
    ) -> Out:
        binding = self.catalog.binding(item)
        if not item.entry:
            raise StepRuleBroken(f"操作 {item.name} 是内部操作，只能由其他模块调用")
        deadline = asyncio.get_running_loop().time() + item.timeout
        scope = Scope(self, caller, request_id, job_id, deadline, tx=Transaction())
        run = self.open_run(binding, scope, None, None)
        scope.root_id = run.id
        if on_start is not None:
            on_start(run.id)
        try:
            check_access(item, caller)
            async with asyncio.timeout_at(deadline):
                result = await execute(binding, input, scope, run)
            await self.commit(scope.tx, run, before_commit, result)
            await self.close_run(run, "ok")
            return cast(Out, result)
        except BaseException as error:
            problem = await self.settle(scope.tx, run, error)
            if problem is error:
                raise
            raise problem from error
        finally:
            await scope.tx.close()

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
        run.writes = "in_parent" if scope.tx.connection else "none"
        await self.close_run(run, "ok")
        return cast(Out, result)

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
    # 提交本身出错时无法确认是否已保存，报告“结果待核对”。
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


# 检查调用者能否执行操作：没有身份时报未登录，有身份但缺权限时报无权限。
def check_access(item: Contract[Any, Any], caller: Caller) -> None:
    if caller.can(item.access):
        return
    if caller.kind == "anonymous":
        raise NotSignedIn(f"「{item.title}」需要登录或服务密钥")
    raise NotAllowed(f"没有权限执行「{item.title}」，需要权限 {item.access}")


# 把超时、数据库断连、只读违规等异常转成框架的错误种类。
def translate(error: BaseException) -> BaseException:
    if isinstance(error, BusinessError) or not isinstance(error, Exception):
        return error
    if isinstance(error, TimeoutError):
        return RunTimeout("处理超时，已停止等待；已经发出的外部操作可能仍在进行")
    if is_readonly_violation(error):
        return StepRuleBroken("没有声明 saves=True 的步骤试图写入数据库")
    if is_unavailable(error):
        return DatabaseUnavailable()
    return error


# 把错误信息写进运行记录。
def fill_error(run: RunRecord, problem: BaseException) -> None:
    failed = next((step for step in reversed(run.steps) if step.status == "failed"), None)
    run.failed_step = failed.title if failed else ""
    if isinstance(problem, BusinessError):
        run.error_code, run.error_kind, run.error_message = (
            problem.code,
            problem.kind,
            problem.detail,
        )
    elif isinstance(problem, asyncio.CancelledError):
        run.error_code, run.error_kind, run.error_message = "cancelled", "cancelled", "执行被取消"
    else:
        run.error_code, run.error_kind = type(problem).__name__, "unexpected"
        run.error_message = (
            failed.error_message if failed else ""
        ) or f"程序异常：{type(problem).__name__}"
