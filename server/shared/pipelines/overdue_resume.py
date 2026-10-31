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


async def resume(connection: AsyncConnection, queue: "JobQueue", root: dict) -> str:
    await ensure_boundary(connection, root["id"])
    pipeline = queue.catalog.pipelines.get(root["pipeline"])
    if pipeline is None:
        raise InvalidInput("当前代码未登记此流程")
    stage = next((stage for stage in pipeline.stages if stage.name == root["current_stage"]), None)
    if stage is None:
        raise InvalidInput("当前阶段的执行配置已改变，请先迁移已保存的数据并确认格式")
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
        .values(
            state=state, reason="人工继续执行已超时流程，仍保留超时记录", updated_at=business_now()
        )
    )
    return "已继续执行超时流程，保留已有结果和恢复位置"


async def restore_job(connection: AsyncConnection, queue: "JobQueue", job_id: str) -> None:
    row = (await connection.execute(select(jobs).where(jobs.c.id == job_id))).mappings().one()
    if row["state"] == "unknown":
        raise InvalidInput("任务对外发送的请求结果待确认，请先查询原请求的执行结果")
    if row["state"] in ("queued", "waiting_retry"):
        return
    if row["state"] != "blocked":
        raise InvalidInput("当前任务不是因流程超时而暂停的任务")
    binding, plan = queue.catalog.find(row["contract"]), queue.catalog.plan(row["contract"])
    if binding is None or plan is None:
        raise InvalidInput("当前代码未登记此操作")
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
        raise InvalidInput("仍有阶段或并行子任务正在执行，请等当前批次结束后继续")
