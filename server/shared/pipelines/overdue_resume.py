"""
人工继续逾期暂停：保留已完成阶段和当前游标，不重复正在执行的动作。
"""

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import InvalidInput
from shared.jobs.queue import reserve
from shared.jobs.tables import jobs
from shared.pipelines.plan import FanOut
from shared.pipelines.tables import members, runs, stages
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue


# 当前真实执行仍在进行时不重排，普通阶段和成员都在明确提交边界恢复。
async def resume(connection: AsyncConnection, queue: "JobQueue", root: dict) -> str:
    await ensure_boundary(connection, root["id"])
    pipeline = queue.catalog.pipelines.get(root["pipeline"])
    if pipeline is None:
        raise InvalidInput("流程当前没有登记")
    stage = next((stage for stage in pipeline.stages if stage.name == root["current_stage"]), None)
    if stage is None:
        raise InvalidInput("当前阶段声明变化，请先迁移并确认格式")
    parent = dict(
        (
            await connection.execute(
                select(stages).where(
                    stages.c.pipeline_id == root["id"], stages.c.name == stage.name
                )
            )
        )
        .mappings()
        .one()
    )
    if isinstance(stage, FanOut) and parent["output_json"] is not None:
        state = "waiting_members"
        await restore_members(connection, queue, parent)
    else:
        state = "running"
        await restore_job(connection, queue, parent["job_id"])
        await connection.execute(
            update(stages).where(stages.c.id == parent["id"]).values(state="queued", error="")
        )
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(state=state, reason="人工继续逾期流程，保留逾期事实", updated_at=business_now())
    )
    return "已继续逾期流程，已有产出和游标保留"


# 暂停的任务只恢复原任务；未知结果仍拒绝重复，不能借逾期绕过核实。
async def restore_job(connection: AsyncConnection, queue: "JobQueue", job_id: str) -> None:
    row = (await connection.execute(select(jobs).where(jobs.c.id == job_id))).mappings().one()
    if row["state"] == "unknown":
        raise InvalidInput("任务外部结果待确认，先处理未知结果")
    if row["state"] in ("queued", "waiting_retry"):
        return
    if row["state"] != "blocked":
        raise InvalidInput("当前任务并非明确的逾期暂停任务")
    binding, plan = queue.catalog.find(row["contract"]), queue.catalog.plan(row["contract"])
    if binding is None or plan is None:
        raise InvalidInput("当前操作未登记")
    await reserve(connection, binding.contract, plan.max_queued)
    await connection.execute(
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(
            state="queued",
            run_after=business_now(),
            finished_at=None,
            lease_until=None,
            updated_at=business_now(),
            error_code="",
            error_message="",
        )
    )


# 成员队列中只有确实暂停的任务恢复，不重跑成功成员。
async def restore_members(connection: AsyncConnection, queue: "JobQueue", parent: dict) -> None:
    rows = (
        (
            await connection.execute(
                select(members).where(
                    members.c.stage_id == parent["id"], members.c.state == "version_blocked"
                )
            )
        )
        .mappings()
        .all()
    )
    for member in rows:
        await restore_job(connection, queue, member["job_id"])
        await connection.execute(
            update(members)
            .where(members.c.id == member["id"])
            .values(state="queued", error="", updated_at=business_now())
        )
    await connection.execute(
        update(stages).where(stages.c.id == parent["id"]).values(state="waiting_members", error="")
    )


# 人工继续只发生在当前批次已经结束的边界，避免与在途动作重叠。
async def ensure_boundary(connection: AsyncConnection, run_id: str) -> None:
    active = await connection.scalar(
        select(jobs.c.id)
        .join(stages, jobs.c.id == stages.c.job_id)
        .where(
            stages.c.pipeline_id == run_id,
            jobs.c.state == "running",
            jobs.c.lease_until > business_now(),
        )
        .limit(1)
    )
    child = await connection.scalar(
        select(jobs.c.id)
        .join(members, jobs.c.id == members.c.job_id)
        .where(
            members.c.pipeline_id == run_id,
            jobs.c.state == "running",
            jobs.c.lease_until > business_now(),
        )
        .limit(1)
    )
    if active or child:
        raise InvalidInput("仍有阶段或成员在执行，请等当前批次收尾后继续")
