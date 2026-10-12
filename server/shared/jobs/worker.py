"""
worker：循环领取任务，通过执行器运行对应的操作，并按结果更新任务状态。
执行期间定期延长执行期限；收到停止信号后不再领取新任务，有限等待在途任务，其余交给期限过期后的恢复处理。
"""

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller, caller_from_record
from shared.access.keys import ApiKeyConfig, current_caller
from shared.data.models import Data
from shared.errors.details import safe_exception_text
from shared.errors.framework import StaleAttempt
from shared.errors.kinds import BusinessError
from shared.flow.runtime import Runtime
from shared.jobs.execution import invoke
from shared.jobs.failures import guarded, save_business_failure
from shared.jobs.failures import next_state as next_state
from shared.jobs.health import WorkerHealth
from shared.jobs.imports import check_import_source
from shared.jobs.queue import JobQueue, Ticket
from shared.jobs.schedule import Scheduler
from shared.pipelines.context import ExecutionContext
from shared.pipelines.runner import prepare as prepare_stage
from shared.timing.clock import Clock
from shared.timing.current import clocked, sleep, wait_or_stop
from shared.timing.current import now as business_now

log = logging.getLogger("server.jobs")

RECLAIM_SECONDS = 15.0
CLEAN_SECONDS = 3600.0


# 后台进程的并发、查询间隔、退出等待与记录保留设置。
@dataclass
class WorkerOptions:
    concurrency: int = 4
    poll_seconds: float = 1.0
    shutdown_seconds: float = 20.0
    record_days: int = 14
    managed_retention: bool = False
    health_file: str = ""
    schedule_org_id: str = ""
    schedule_org_ids: tuple[str, ...] = ()


# 领取并执行后台任务，保存结果并处理退出和重试。
class Worker:
    # 所有辅助函数继承所属应用时钟，不保留第二份时间状态。
    @property
    def clock(self) -> Clock:
        return self.runtime.clock

    # 绑定执行器、任务表、服务密钥配置和运行参数。
    def __init__(
        self, runtime: Runtime, queue: JobQueue, keys: list[ApiKeyConfig], options: WorkerOptions
    ) -> None:
        self.runtime = runtime
        self.queue = queue
        self.keys = keys
        self.options = options
        self.scheduler = Scheduler(
            runtime.catalog.schedules,
            queue,
            runtime.database,
            options.schedule_org_id,
            options.schedule_org_ids,
        )
        self.tasks: set[asyncio.Task[None]] = set()
        self.segmented_tasks: set[asyncio.Task[None]] = set()
        self.stop = asyncio.Event()
        self.health = WorkerHealth(options.health_file)
        self.cycle_failed = False

    # 本轮领取或维护失败时不刷新健康信号。
    def failed_cycle(self) -> None:
        self.cycle_failed = True

    # 主循环：处理过期任务、登记定时任务、领取并执行任务，直到收到停止信号。
    @clocked
    async def run(self, stop: asyncio.Event) -> None:
        self.health.clear()
        try:
            await self.loop(stop)
        finally:
            self.health.clear()

    # 正常空队列也报告健康；领取或维护失败时保留上次成功时间。
    @clocked
    async def loop(self, stop: asyncio.Event) -> None:
        self.stop = stop
        next_reclaim = next_clean = 0.0
        while not stop.is_set():
            self.cycle_failed = False
            now = business_now()
            if now >= next_reclaim:
                await guarded("reclaim", self.queue.reclaim(now), self.failed_cycle)
                next_reclaim = now + RECLAIM_SECONDS
            if now >= next_clean and not self.options.managed_retention:
                cutoff = now - self.options.record_days * 86400
                await guarded("clean", self.runtime.recorder.store.clean(cutoff), self.failed_cycle)
                next_clean = now + CLEAN_SECONDS
            await guarded("schedule", self.scheduler.tick(now), self.failed_cycle)
            await guarded("pipelines", self.queue.pipelines.reconcile(), self.failed_cycle)
            claimed = await self.claim_some()
            if not self.cycle_failed:
                self.health.touch()
            if not claimed:
                await wait_or_stop(stop, self.options.poll_seconds)
        await self.drain()

    # 在并发上限内领取任务；领取到任何任务返回 True。
    @clocked
    async def claim_some(self) -> bool:
        claimed = False
        while len(self.tasks) < self.options.concurrency and not self.stop.is_set():
            ticket = await guarded("claim", self.queue.claim(business_now()), self.failed_cycle)
            if ticket is None:
                break
            task = asyncio.create_task(self.execute(ticket))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            plan = self.runtime.catalog.plan(ticket.contract)
            if plan is not None and plan.segmented:
                self.segmented_tasks.add(task)
                task.add_done_callback(self.segmented_tasks.discard)
            claimed = True
        return claimed

    # 停止时有限等待在途任务，超时后取消并等待回滚、连接归还完成。
    @clocked
    async def drain(self) -> None:
        if not self.tasks:
            return
        tasks = tuple(self.tasks)
        _, pending = await asyncio.wait(tasks, timeout=self.options.shutdown_seconds)
        for task in pending - self.segmented_tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cancelled = sum(task.cancelled() for task in tasks)
        log.info("worker_stopped finished=%s cancelled=%s", len(tasks) - cancelled, cancelled)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                raise result

    # 执行一个任务并更新状态。
    @clocked
    async def execute(self, ticket: Ticket) -> None:
        try:
            context = await prepare_stage(self.queue, ticket)
        except StaleAttempt:
            log.warning("job_attempt_stale job_id=%s attempt=%s", ticket.id, ticket.attempt)
            return
        if context is not None and not context.allowed:
            return
        binding = self.runtime.catalog.find(ticket.contract)
        plan = self.runtime.catalog.plan(ticket.contract)
        if binding is None or plan is None:
            await self.queue.fail(
                ticket, "failed", "not_registered", "任务对应的操作没有登记或模块未启用"
            )
            return
        if not await check_import_source(self.queue, ticket, plan):
            return
        if context is None and ticket.module_version != binding.module.version:
            message = (
                f"任务按模块版本 {ticket.module_version} 登记，当前是 {binding.module.version}；"
                "需要人工确认后再执行"
            )
            await self.queue.fail(ticket, "blocked", "version_changed", message)
            return
        try:
            input = binding.contract.input.model_validate_json(ticket.input_json)
        except ValidationError:
            await self.queue.fail(
                ticket,
                "failed",
                "input_invalid",
                "任务输入与当前格式不符，请按当前规则重新登记任务",
            )
            return
        caller = self.restore_caller(ticket)
        if caller is None:
            await self.queue.fail(ticket, "failed", "not_allowed", "登记任务的服务密钥已不存在")
            return
        heartbeat = asyncio.create_task(
            self.keep_lease(ticket, plan.lease_seconds, asyncio.current_task())
        )
        try:
            await self.run_job(
                ticket, input, caller, plan.retry.times, plan.retry.wait_after, context
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    # 通过执行器运行任务；完成标记与业务写入同一事务提交。
    @clocked
    async def run_job(
        self,
        ticket: Ticket,
        input: Data,
        caller: Caller,
        retries: int,
        wait_after: Any,
        context: ExecutionContext | None = None,
    ) -> None:
        # 在提交前把任务标为完成；尝试已过期时放弃本次写入。
        async def finish(connection: AsyncConnection, result: Data, run_id: str) -> None:
            if context is not None:
                await context.finish(connection, result, run_id)
            elif not await self.queue.finish(connection, ticket, result.model_dump_json(), run_id):
                raise StaleAttempt()

        try:
            await invoke(
                self.runtime,
                self.queue,
                ticket,
                input,
                caller,
                self.stop,
                self.options.shutdown_seconds,
                finish,
                context.observation_position if context else None,
            )
        except StaleAttempt:
            log.warning("job_attempt_stale job_id=%s attempt=%s", ticket.id, ticket.attempt)
        except BusinessError as error:
            await save_business_failure(self.queue, ticket, error, retries, wait_after)
        except Exception as error:
            run_id = str(getattr(error, "run_id", ""))
            await self.queue.fail(
                ticket,
                "failed",
                type(error).__name__,
                f"程序异常：{type(error).__name__}",
                run_id=run_id,
            )
            log.error(
                "job_failed job_id=%s run_id=%s error=%s",
                ticket.id,
                run_id,
                safe_exception_text(error),
            )

    # 恢复登记任务时的调用者；服务密钥按当前配置重新取得权限。
    def restore_caller(self, ticket: Ticket) -> Caller | None:
        caller = caller_from_record(json.loads(ticket.caller_json))
        if caller.kind == "service":
            current = current_caller(caller.name, self.keys)
            return current if current and current.org_id == caller.org_id else None
        return caller

    # 定期延长执行期限；任务已不属于本次尝试时取消执行。
    @clocked
    async def keep_lease(
        self, ticket: Ticket, lease: float, runner: asyncio.Task[Any] | None
    ) -> None:
        while True:
            await sleep(lease / 3)
            plan = self.runtime.catalog.plan(ticket.contract)
            owned = await guarded(
                "extend",
                self.queue.extend(
                    ticket, business_now() + lease, require_current=bool(plan and plan.segmented)
                ),
            )
            if owned is False and runner is not None:
                log.warning("job_lease_lost job_id=%s", ticket.id)
                runner.cancel()
                return
