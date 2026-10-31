from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.jobs import resources
from shared.jobs.checkpoint_store import may_resume
from shared.jobs.tables import jobs
from shared.modules.catalog import Catalog
from shared.pipelines.failure import recoverable_wait


async def expire(
    connection: AsyncConnection,
    catalog: Catalog,
    job_id: str,
    name: str,
    attempt: int,
    now: float,
    pipeline_job: bool = False,
) -> None:
    from shared.jobs.queue import release

    plan = catalog.plan(name)
    values: dict[str, Any] = {"updated_at": now, "lease_until": None}
    safe_wait = (
        pipeline_job
        and plan is not None
        and plan.repeat_safe
        and await recoverable_wait(connection, catalog, job_id)
    )
    if safe_wait or await may_resume(connection, plan, job_id, attempt):
        values |= {"state": "waiting_retry", "run_after": now, "error_code": "lease_expired"}
        values["error_message"] = (
            "任务占用有效期已过（worker 可能已退出）；任务可以安全继续执行，已重新排队"
        )
    else:
        values |= {"state": "unknown", "finished_at": now, "error_code": "lease_expired"}
        values["error_message"] = (
            "任务占用有效期已过，无法确认任务是否已产生实际结果，请人工检查后再决定是否重试"
        )
    await connection.execute(update(jobs).where(jobs.c.id == job_id).values(**values))
    await resources.release(connection, job_id, attempt, now)
    if values["state"] == "unknown":
        await release(connection, name)
