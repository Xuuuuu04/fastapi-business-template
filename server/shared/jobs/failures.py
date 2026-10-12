"""
后台失败与维护错误处理，未知结果不进入自动重试，维护失败保留失败事实。
"""

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from shared.errors.framework import StepRuleBroken
from shared.errors.kinds import RETRY_KINDS, BusinessError, Kind
from shared.jobs.defer import RetryLater
from shared.jobs.resources import cool
from shared.timing.current import now as business_now

log = logging.getLogger("server.jobs")

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue, Ticket


# 根据错误种类和已尝试次数决定下一个状态。
def next_state(kind: Kind, attempt: int, retries: int, wait_after: Any) -> tuple[str, float]:
    if kind in RETRY_KINDS and attempt <= retries:
        return "waiting_retry", business_now() + float(wait_after(attempt))
    if kind == Kind.UNKNOWN_RESULT:
        return "unknown", 0.0
    return "failed", 0.0


# 明确延后不计作失败；外部效果已产生时执行器会先把RetryLater转为未知结果。
async def save_business_failure(
    queue: "JobQueue", ticket: "Ticket", error: BusinessError, retries: int, wait_after: Any
) -> None:
    if isinstance(error, RetryLater):
        until = queue.clock.now() + error.seconds
        plan = queue.catalog.plan(ticket.contract)
        names = {resource.name for resource in plan.resources} if plan else set()
        if error.resource and error.resource not in names:
            raise StepRuleBroken("延后的资源没有在JobPlan.resources声明")
        if error.resource:
            async with queue.database.write() as connection:
                await cool(connection, error.resource, until)
        await queue.fail(
            ticket,
            "waiting_retry",
            error.code,
            error.detail,
            run_after=until,
            run_id=error.run_id,
            deferred=True,
        )
        return
    failures = ticket.failed_attempts + 1 if ticket.failed_attempts is not None else ticket.attempt
    state, run_after = next_state(error.kind, failures, retries, wait_after)
    await queue.fail(
        ticket, state, error.code, error.detail, run_after=run_after, run_id=error.run_id
    )


# 执行一项后台维护，出错只写日志，避免 worker 主循环退出。
async def guarded[T](
    name: str, work: Awaitable[T], on_failure: Callable[[], None] | None = None
) -> T | None:
    try:
        return await work
    except Exception:
        if on_failure is not None:
            on_failure()
        log.exception("worker_%s_failed", name)
        return None
