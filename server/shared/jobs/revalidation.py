"""
任务领取后、执行前重新核对有效期与关键业务状态，不把排队时的状态当成现在仍然有效。
"""

from typing import TYPE_CHECKING

from sqlalchemy import select

from shared.access.caller import Caller
from shared.data.models import Data
from shared.jobs.limits import Validity
from shared.jobs.tables import jobs

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime
    from shared.jobs.queue import JobQueue, Ticket


# 所有核对在实际业务执行与写事务之前完成，查询操作也留下自己的运行证据。
async def allowed(
    runtime: "Runtime",
    queue: "JobQueue",
    ticket: "Ticket",
    input: Data,
    caller: Caller,
    deadline: float,
) -> bool:
    async with queue.database.read() as connection:
        row = (
            (
                await connection.execute(
                    select(jobs.c.valid_until, jobs.c.attempt, jobs.c.state).where(
                        jobs.c.id == ticket.id
                    )
                )
            )
            .mappings()
            .first()
        )
    if row is None or row["attempt"] != ticket.attempt or row["state"] != "running":
        return False
    if row["valid_until"] is not None and row["valid_until"] <= runtime.clock.now():
        await queue.fail(ticket, "expired", "task_expired", "执行前业务有效期已过")
        return False
    plan = queue.catalog.plan(ticket.contract)
    if plan is not None and plan.revalidate is not None:
        result = await runtime.run(
            plan.revalidate,
            input,
            caller=caller,
            request_id=ticket.request_id,
            job_id=ticket.id,
            deadline=deadline,
        )
        if not isinstance(result, Validity) or not result.valid:
            reason = result.reason if isinstance(result, Validity) else "核对结果格式不符"
            await queue.fail(ticket, "expired", "task_invalid", reason or "关键业务状态已改变")
            return False
    return True
