"""
成员故障同步到扇出阶段；未知结果和格式变化立即暂停，普通失败收齐其他成员后汇合判断。
"""

import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.pipelines.member_pool import advance
from shared.pipelines.member_store import member_for
from shared.pipelines.plan import FanOut, Wait
from shared.pipelines.storage import root_for
from shared.pipelines.tables import members, runs, stages

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue
    from shared.modules.catalog import Catalog


# 旧任务已不再关联成员时不修改成员当前阶段，成功结果永远保留。
async def failed(
    connection: AsyncConnection,
    queue: "JobQueue",
    job_id: str,
    state: str,
    message: str,
    run_id: str = "",
) -> None:
    member = await member_for(connection, job_id)
    if member is None or member["state"] == "succeeded":
        return
    root = await root_for(connection, member["pipeline_id"])
    parent = dict(
        (await connection.execute(select(stages).where(stages.c.id == member["stage_id"])))
        .mappings()
        .one()
    )
    value = {"blocked": "version_blocked", "waiting_retry": "waiting_external"}.get(state, state)
    if state == "cancelled" and parent["state"] == "joining":
        value = "skipped"
    values: dict[str, Any] = dict(state=value, error=message, updated_at=time.time())
    if run_id:
        values["run_id"] = run_id
    if member["state"] == "running" and member["started_at"]:
        values["elapsed_ms"] = member["elapsed_ms"] + (time.time() - member["started_at"]) * 1000
    await connection.execute(update(members).where(members.c.id == member["id"]).values(**values))
    if state == "unknown":
        await pause(connection, root, parent, "unknown", message)
        return
    if root["state"] in ("unknown", "version_blocked", "overdue_paused"):
        return
    if state == "blocked":
        await pause(connection, root, parent, "version_blocked", message)
        return
    pipeline = queue.catalog.pipelines.get(root["pipeline"])
    group = (
        next((s for s in pipeline.stages if s.name == parent["name"]), None) if pipeline else None
    )
    if isinstance(group, FanOut):
        await advance(connection, queue, root, parent, group)


# 未知状态不会被其他成员的普通故障覆盖，外部结果必须人工核实。
async def pause(
    connection: AsyncConnection, root: dict, parent: dict, state: str, message: str
) -> None:
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(state=state, reason=message, updated_at=time.time())
    )
    await connection.execute(
        update(stages).where(stages.c.id == parent["id"]).values(state=state, error=message)
    )


# 等待次数不是错误重试次数，租约恢复继续使用原等待截止时间。
async def recoverable_wait(connection: AsyncConnection, catalog: "Catalog", job_id: str) -> bool:
    member = await member_for(connection, job_id)
    if member is None:
        return False
    root = await root_for(connection, member["pipeline_id"])
    parent = (
        await connection.execute(select(stages.c.name).where(stages.c.id == member["stage_id"]))
    ).scalar_one()
    pipeline = catalog.pipelines.get(root["pipeline"])
    group = (
        next((stage for stage in pipeline.stages if stage.name == parent), None)
        if pipeline
        else None
    )
    return isinstance(group, FanOut) and any(
        child.name == member["phase_name"] and isinstance(child, Wait) for child in group.stages
    )
