"""
worker：循环领取任务，通过执行器运行对应的操作，并按结果更新任务状态。
执行期间定期延长执行期限；收到停止信号后不再领取新任务，有限等待在途任务，其余交给期限过期后的恢复处理。
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller, caller_from_record
from shared.access.keys import ApiKeyConfig, current_caller
from shared.data.models import Data
from shared.errors.framework import StaleAttempt
from shared.errors.kinds import RETRY_KINDS, BusinessError, Kind
from shared.flow.runtime import Runtime
from shared.jobs.queue import JobQueue, Ticket
from shared.jobs.schedule import Scheduler

log = logging.getLogger("server.jobs")

RECLAIM_SECONDS = 15.0
CLEAN_SECONDS = 3600.0


@dataclass
class WorkerOptions:
    concurrency: int = 4
    poll_seconds: float = 1.0
    shutdown_seconds: float = 20.0
    record_days: int = 14


class Worker:
    # 绑定执行器、任务表、服务密钥配置和运行参数。
    def __init__(
        self, runtime: Runtime, queue: JobQueue, keys: list[ApiKeyConfig], options: WorkerOptions
    ) -> None:
        self.runtime = runtime
        self.queue = queue
        self.keys = keys
        self.options = options
        self.scheduler = Scheduler(runtime.catalog.schedules, queue, runtime.database)
        self.tasks: set[asyncio.Task[None]] = set()

    # 主循环：处理过期任务、登记定时任务、领取并执行任务，直到收到停止信号。
    async def run(self, stop: asyncio.Event) -> None:
        next_reclaim = next_clean = 0.0
        while not stop.is_set():
            now = time.time()
            if now >= next_reclaim:
                await guarded("reclaim", self.queue.reclaim(now))
                next_reclaim = now + RECLAIM_SECONDS
            if now >= next_clean:
                cutoff = now - self.options.record_days * 86400
                await guarded("clean", self.runtime.recorder.store.clean(cutoff))
                next_clean = now + CLEAN_SECONDS
            await guarded("schedule", self.scheduler.tick(now))
            if not await self.claim_some():
                await wait_or_stop(stop, self.options.poll_seconds)
        await self.drain()

    # 在并发上限内领取任务；领取到任何任务返回 True。
    async def claim_some(self) -> bool:
        claimed = False
        while len(self.tasks) < self.options.concurrency:
            ticket = await guarded("claim", self.queue.claim(time.time()))
            if ticket is None:
                break
            task = asyncio.create_task(self.execute(ticket))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            claimed = True
        return claimed

    # 停止时有限等待在途任务，超时后取消它们。
    async def drain(self) -> None:
        if not self.tasks:
            return
        done, pending = await asyncio.wait(self.tasks, timeout=self.options.shutdown_seconds)
        for task in pending:
            task.cancel()
        log.info("worker_stopped finished=%s cancelled=%s", len(done), len(pending))

    # 执行一个任务并更新状态。
    async def execute(self, ticket: Ticket) -> None:
        binding = self.runtime.catalog.find(ticket.contract)
        plan = self.runtime.catalog.plan(ticket.contract)
        if binding is None or plan is None:
            await self.queue.fail(
                ticket, "failed", "not_registered", "任务对应的操作没有登记或模块未启用"
            )
            return
        if ticket.module_version != binding.module.version:
            message = (
                f"任务按模块版本 {ticket.module_version} 登记，当前是 {binding.module.version}；"
                "需要人工确认后再执行"
            )
            await self.queue.fail(ticket, "blocked", "version_changed", message)
            return
        try:
            input = binding.contract.input.model_validate_json(ticket.input_json)
        except ValidationError as error:
            await self.queue.fail(
                ticket, "failed", "input_invalid", f"任务输入与当前格式不符：{error}"
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
            await self.run_job(ticket, input, caller, plan.retry.times, plan.retry.wait_after)
        finally:
            heartbeat.cancel()

    # 通过执行器运行任务；完成标记与业务写入同一事务提交。
    async def run_job(
        self, ticket: Ticket, input: Data, caller: Caller, retries: int, wait_after: Any
    ) -> None:
        binding = self.runtime.catalog.by_name[ticket.contract]

        # 在提交前把任务标为完成；尝试已过期时放弃本次写入。
        async def finish(connection: AsyncConnection, result: Data, run_id: str) -> None:
            if not await self.queue.finish(connection, ticket, result.model_dump_json(), run_id):
                raise StaleAttempt()

        try:
            await self.runtime.run(
                binding.contract,
                input,
                caller=caller,
                request_id=ticket.request_id,
                job_id=ticket.id,
                before_commit=finish,
            )
        except StaleAttempt:
            log.warning("job_attempt_stale job_id=%s attempt=%s", ticket.id, ticket.attempt)
        except BusinessError as error:
            state, run_after = next_state(error.kind, ticket.attempt, retries, wait_after)
            await self.queue.fail(
                ticket, state, error.code, error.detail, run_after=run_after, run_id=error.run_id
            )
        except Exception as error:
            run_id = str(getattr(error, "run_id", ""))
            await self.queue.fail(
                ticket, "failed", type(error).__name__, f"程序异常：{error}"[:500], run_id=run_id
            )

    # 恢复登记任务时的调用者；服务密钥按当前配置重新取得权限。
    def restore_caller(self, ticket: Ticket) -> Caller | None:
        caller = caller_from_record(json.loads(ticket.caller_json))
        if caller.kind == "service":
            return current_caller(caller.name, self.keys)
        return caller

    # 定期延长执行期限；任务已不属于本次尝试时取消执行。
    async def keep_lease(
        self, ticket: Ticket, lease: float, runner: asyncio.Task[Any] | None
    ) -> None:
        while True:
            await asyncio.sleep(lease / 3)
            owned = await guarded("extend", self.queue.extend(ticket, time.time() + lease))
            if owned is False and runner is not None:
                log.warning("job_lease_lost job_id=%s", ticket.id)
                runner.cancel()
                return


# 根据错误种类和已尝试次数决定下一个状态。
def next_state(kind: Kind, attempt: int, retries: int, wait_after: Any) -> tuple[str, float]:
    if kind in RETRY_KINDS and attempt <= retries:
        return "waiting_retry", time.time() + float(wait_after(attempt))
    if kind == Kind.UNKNOWN_RESULT:
        return "unknown", 0.0
    return "failed", 0.0


# 执行一项后台维护，出错只写日志，避免 worker 主循环退出。
async def guarded[T](name: str, work: Awaitable[T]) -> T | None:
    try:
        return await work
    except Exception:
        log.exception("worker_%s_failed", name)
        return None


# 等待一段时间，或在收到停止信号时提前返回。
async def wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        return
