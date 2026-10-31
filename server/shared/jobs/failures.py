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


def next_state(kind: Kind, attempt: int, retries: int, wait_after: Any) -> tuple[str, float]:
    if kind in RETRY_KINDS and attempt <= retries:
        return "waiting_retry", business_now() + float(wait_after(attempt))
    if kind == Kind.UNKNOWN_RESULT:
        return "unknown", 0.0
    return "failed", 0.0


async def save_business_failure(
    queue: "JobQueue", ticket: "Ticket", error: BusinessError, retries: int, wait_after: Any
) -> None:
    if isinstance(error, RetryLater):
        until = queue.clock.now() + error.seconds
        plan = queue.catalog.plan(ticket.contract)
        names = {resource.name for resource in plan.resources} if plan else set()
        if error.resource and error.resource not in names:
            raise StepRuleBroken("需要延后使用的资源未在 JobPlan.resources 中声明")
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
    failures = ticket.failed_attempts + 1
    state, run_after = next_state(error.kind, failures, retries, wait_after)
    await queue.fail(
        ticket, state, error.code, error.detail, run_after=run_after, run_id=error.run_id
    )


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
