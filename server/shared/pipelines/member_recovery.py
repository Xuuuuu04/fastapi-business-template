import json
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import InvalidInput
from shared.jobs.tables import checkpoints, jobs
from shared.pipelines.member_compat import group_compatible, member_compatible
from shared.pipelines.member_pool import advance
from shared.pipelines.plan import FanOut, Pipeline
from shared.pipelines.schema import declarations, stage_declaration
from shared.pipelines.storage import ACTIVE
from shared.pipelines.tables import members, runs, stages
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue


async def resume(
    connection: AsyncConnection,
    queue: "JobQueue",
    root: dict,
    parent: dict,
    pipeline: Pipeline,
    group: FanOut,
    accept_schema: bool,
    confirm_unknown: bool,
) -> str:
    await validate_resume(
        connection, queue, root, parent, pipeline, group, accept_schema, confirm_unknown
    )
    rows = (
        (await connection.execute(select(members).where(members.c.stage_id == parent["id"])))
        .mappings()
        .all()
    )
    for row in rows:
        await restore_member(connection, queue, dict(row), group, accept_schema, confirm_unknown)
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(
            state="waiting_members",
            declarations_json=json.dumps(declarations(pipeline, queue.catalog)),
            finished_at=None,
            updated_at=business_now(),
            reason="人工恢复失败的子任务，复用已成功的结果",
        )
    )
    await connection.execute(
        update(stages)
        .where(stages.c.id == parent["id"])
        .values(state="waiting_members", error="", finished_at=None)
    )
    root.update(
        state="waiting_members", declarations_json=json.dumps(declarations(pipeline, queue.catalog))
    )
    parent["state"] = "waiting_members"
    await advance(connection, queue, root, parent, group)
    return "已恢复失败的子任务；成功的子任务和已完成阶段不会重新执行"


async def validate_resume(
    connection: AsyncConnection,
    queue: "JobQueue",
    root: dict,
    parent: dict,
    pipeline: Pipeline,
    group: FanOut,
    accept_schema: bool,
    confirm_unknown: bool,
) -> None:
    if root["state"] not in ("failed", "unknown", "version_blocked"):
        raise InvalidInput("此并行阶段尚未失败或暂停，不能重新执行")
    if root["state"] == "unknown" and not confirm_unknown:
        raise InvalidInput("子任务对外发送的请求结果待确认，请先核实原请求是否已执行")
    if not accept_schema and not group_compatible(root, group, pipeline, queue.catalog):
        raise InvalidInput("子任务结果的汇总配置或后续阶段格式已改变，需要明确接受当前格式")
    executing = await connection.scalar(
        select(jobs.c.id)
        .join(members, members.c.job_id == jobs.c.id)
        .where(
            members.c.stage_id == parent["id"],
            jobs.c.state == "running",
            jobs.c.lease_until > business_now(),
        )
        .limit(1)
    )
    if executing:
        raise InvalidInput("仍有子任务正在执行，请等当前操作结束后恢复")
    other = await connection.scalar(
        select(runs.c.id).where(
            runs.c.pipeline == root["pipeline"],
            runs.c.org_id == root["org_id"],
            runs.c.id != root["id"],
            runs.c.state.in_(ACTIVE),
        )
    )
    if other:
        raise InvalidInput(f"同一组织的另一周期 {other} 仍在执行")


async def restore_member(
    connection: AsyncConnection,
    queue: "JobQueue",
    member: dict,
    group: FanOut,
    accept_schema: bool,
    confirm_unknown: bool,
) -> None:
    from shared.pipelines.recovery import validate_checkpoint, validate_saved

    if member["state"] == "succeeded":
        validate_saved(
            group.stages[-1].operation.output, member["output_json"], member["key"] + "输出"
        )
        return
    if member["state"] == "skipped":
        return
    if not member_compatible(member, group, queue.catalog) and not accept_schema:
        raise InvalidInput(f"子任务 {member['key']} 的后续阶段格式已改变，需要明确接受当前格式")
    child = next((child for child in group.stages if child.name == member["phase_name"]), None)
    if child is None:
        raise InvalidInput(f"子任务 {member['key']} 当前所在阶段已移除，需要迁移后恢复")
    validate_saved(child.operation.input, member["current_input_json"], member["key"] + "输入")
    plan = queue.catalog.plan(child.operation.name)
    assert plan is not None
    if member["job_id"] is not None:
        job = (
            (await connection.execute(select(jobs).where(jobs.c.id == member["job_id"])))
            .mappings()
            .one()
        )
        if job["contract"] != child.operation.name:
            raise InvalidInput(f"子任务 {member['key']} 的操作名称已改变，需要迁移当前任务")
        await validate_checkpoint(connection, member["job_id"], plan, member["key"])
    declared = json.dumps([stage_declaration(child, queue.catalog) for child in group.stages])
    values = dict(declarations_json=declared, updated_at=business_now())
    if member["state"] in ("failed", "unknown", "version_blocked", "cancelled"):
        values |= dict(state="planned", error="", finished_at=None, wait_until=None)
    await connection.execute(update(members).where(members.c.id == member["id"]).values(**values))
    if member["state"] == "unknown" and confirm_unknown:
        await connection.execute(
            update(checkpoints)
            .where(checkpoints.c.job_id == member["job_id"])
            .values(external_pending=False)
        )
