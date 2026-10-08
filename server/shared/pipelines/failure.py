"""
后台失败、重试和租约恢复同步流程状态，避免任务失败而流程仍假装运行。
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue
    from shared.modules.catalog import Catalog

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.pipelines.plan import Wait
from shared.pipelines.storage import root_for, stage_for
from shared.pipelines.tables import runs, stages


# 在任务状态更新的同一事务记录阶段状态，已结束的成功阶段不被旧尝试覆盖。
async def failed(
    connection: AsyncConnection,
    queue: "JobQueue",
    job_id: str,
    state: str,
    message: str,
    run_id: str = "",
) -> None:
    stage = await stage_for(connection, job_id)
    if stage is None or stage["state"] == "succeeded":
        return
    root = await root_for(connection, stage["pipeline_id"])
    if root["current_stage"] != stage["name"]:
        return
    value = "version_blocked" if state == "blocked" else state
    root_state = "waiting_external" if state == "waiting_retry" else value
    values: dict[str, object] = dict(state=value, error=message)
    if stage["state"] == "running" and stage["started_at"] is not None:
        values["elapsed_ms"] = stage["elapsed_ms"] + (time.time() - stage["started_at"]) * 1000
    if run_id:
        values["run_id"] = run_id
    await connection.execute(update(stages).where(stages.c.id == stage["id"]).values(**values))
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(
            state=root_state,
            updated_at=time.time(),
            reason=message,
            finished_at=time.time() if state in ("failed", "cancelled") else None,
        )
    )
    if state in ("failed", "cancelled"):
        await queue.pipelines.next_cycle(connection, root)


# Wait的检查次数不当作故障重试次数；超时仍由准备阶段明确终止。
async def recoverable_wait(connection: AsyncConnection, catalog: "Catalog", job_id: str) -> bool:
    stage = await stage_for(connection, job_id)
    if stage is None:
        return False
    root = await root_for(connection, stage["pipeline_id"])
    pipeline = catalog.pipelines.get(root["pipeline"])
    if pipeline is None:
        return False
    return any(s.name == stage["name"] and isinstance(s, Wait) for s in pipeline.stages)
