import json
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import caller_from_record
from shared.errors.framework import InvalidInput, QueueFull
from shared.jobs.tables import jobs
from shared.pipelines.member_compat import block, group_compatible, member_compatible
from shared.pipelines.plan import All, FanOut, Pipeline, Ratio, Wait
from shared.pipelines.tables import members, runs, stages
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue

BUSY = ("queued", "running", "waiting_retry")


async def planned(
    connection: AsyncConnection,
    queue: "JobQueue",
    root: dict,
    row: dict,
    group: FanOut,
    body: str,
    run_id: str,
) -> None:
    if isinstance(group.join, Ratio) and group.join.required:
        keys = set(
            (
                await connection.execute(
                    select(members.c.key).where(
                        members.c.stage_id == row["id"], members.c.key.in_(group.join.required)
                    )
                )
            ).scalars()
        )
        if keys != set(group.join.required):
            raise InvalidInput(f"并行阶段 {group.name} 未登记 Ratio.required 中指定的必需子任务")
    await connection.execute(
        update(stages)
        .where(stages.c.id == row["id"])
        .values(state="waiting_members", output_json=body, run_id=run_id, error="")
    )
    desired = "overdue_paused" if root["state"] == "overdue_paused" else "waiting_members"
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(state=desired, updated_at=business_now(), reason="")
    )
    row.update(state="waiting_members", output_json=body, run_id=run_id)
    root["state"] = desired
    await advance(connection, queue, root, row, group)


async def advance(
    connection: AsyncConnection, queue: "JobQueue", root: dict, row: dict, group: FanOut
) -> None:
    if root["state"] not in ("waiting_members", "running"):
        return
    pipeline = queue.catalog.pipelines[root["pipeline"]]
    if not group_compatible(root, group, pipeline, queue.catalog):
        await block(connection, root, row, "并行子任务的完成条件或后续阶段数据格式已改变")
        return
    counts = await states_of(connection, row["id"])
    if row["state"] != "joining" and await enough(connection, row["id"], group, counts):
        await seal(connection, row["id"])
        row["state"] = "joining"
    active = await active_count(connection, row["id"])
    if row["state"] == "joining":
        if active == 0:
            await completed(connection, queue, root, row, group)
    elif active == 0 and not counts.get("planned", 0):
        await failed_group(connection, queue, root, row, counts)
    else:
        await fill(connection, queue, root, row, group, active)


async def enough(connection: AsyncConnection, stage_id: str, group: FanOut, counts: dict) -> bool:
    total, successful = sum(counts.values()), counts.get("succeeded", 0)
    if isinstance(group.join, All):
        return successful == total
    if successful / max(total, 1) < group.join.success:
        return False
    required = await connection.scalar(
        select(func.count())
        .select_from(members)
        .where(
            members.c.stage_id == stage_id,
            members.c.key.in_(group.join.required),
            members.c.state == "succeeded",
        )
    )
    return required == len(group.join.required)


async def seal(connection: AsyncConnection, stage_id: str) -> None:
    await connection.execute(
        update(members)
        .where(members.c.stage_id == stage_id, members.c.state == "succeeded")
        .values(accepted=True)
    )
    await connection.execute(
        update(members)
        .where(
            members.c.stage_id == stage_id, members.c.state == "planned", members.c.job_id.is_(None)
        )
        .values(state="skipped", updated_at=business_now(), finished_at=business_now())
    )
    await connection.execute(update(stages).where(stages.c.id == stage_id).values(state="joining"))


async def active_count(connection: AsyncConnection, stage_id: str) -> int:
    result = await connection.scalar(
        select(func.count())
        .select_from(members.join(jobs, members.c.job_id == jobs.c.id))
        .where(members.c.stage_id == stage_id, jobs.c.state.in_(BUSY))
    )
    return int(result or 0)


async def states_of(connection: AsyncConnection, stage_id: str) -> dict[str, int]:
    rows = await connection.execute(
        select(members.c.state, func.count())
        .where(members.c.stage_id == stage_id)
        .group_by(members.c.state)
    )
    return {state: int(count) for state, count in rows}


async def fill(
    connection: AsyncConnection,
    queue: "JobQueue",
    root: dict,
    row: dict,
    group: FanOut,
    active: int,
) -> None:
    available = group.max_parallel - active
    if available <= 0:
        return
    pending = (
        (
            await connection.execute(
                select(members)
                .where(members.c.stage_id == row["id"], members.c.state == "planned")
                .order_by(members.c.key)
                .limit(available)
            )
        )
        .mappings()
        .all()
    )
    for member in pending:
        if not member_compatible(dict(member), group, queue.catalog):
            await block(
                connection,
                root,
                row,
                f"子任务 {member['key']} 的阶段 {member['phase_name']} 或后续阶段格式已改变",
            )
            return
        try:
            async with connection.begin_nested():
                await dispatch(connection, queue, root, group, dict(member))
        except QueueFull:
            await connection.execute(
                update(runs)
                .where(runs.c.id == root["id"])
                .values(reason="子任务队列已满，正在等待空位", updated_at=business_now())
            )
            break


async def dispatch(
    connection: AsyncConnection, queue: "JobQueue", root: dict, group: FanOut, member: dict
) -> None:
    from shared.jobs.queue import reserve

    stage = next(child for child in group.stages if child.name == member["phase_name"])
    input = stage.operation.input.model_validate_json(member["current_input_json"])
    if member["job_id"] is None:
        job_id = await queue.submit(
            connection,
            stage.operation,
            input,
            caller_from_record(json.loads(root["caller_json"])),
            key="pipeline:member:" + member["id"] + ":" + stage.name,
            request_id="",
        )
    else:
        job_id = member["job_id"]
        plan = queue.catalog.plan(stage.operation.name)
        assert plan is not None
        await reserve(connection, stage.operation, plan.max_queued)
        await connection.execute(
            update(jobs)
            .where(jobs.c.id == job_id)
            .values(
                state="queued",
                run_after=business_now(),
                lease_until=None,
                finished_at=None,
                updated_at=business_now(),
                error_code="",
                error_message="",
                module_version=queue.catalog.binding(stage.operation).module.version,
            )
        )
    await connection.execute(
        update(members)
        .where(members.c.id == member["id"])
        .values(
            job_id=job_id,
            state="queued",
            error="",
            updated_at=business_now(),
            wait_until=(member["wait_until"] or business_now() + stage.timeout)
            if isinstance(stage, Wait)
            else None,
        )
    )


async def completed(
    connection: AsyncConnection, queue: "JobQueue", root: dict, row: dict, group: FanOut
) -> None:
    pipeline: Pipeline = queue.catalog.pipelines[root["pipeline"]]
    index = next(i for i, stage in enumerate(pipeline.stages) if stage.name == group.name)
    now = business_now()
    await connection.execute(
        update(stages)
        .where(stages.c.id == row["id"])
        .values(state="succeeded", finished_at=now, elapsed_ms=(now - row["started_at"]) * 1000)
    )
    if index + 1 < len(pipeline.stages):
        await queue.pipelines.enqueue(connection, root, pipeline, index + 1)
    else:
        await connection.execute(
            update(runs)
            .where(runs.c.id == root["id"])
            .values(state="succeeded", finished_at=now, updated_at=now, reason="")
        )
        await queue.pipelines.next_cycle(connection, root)


async def failed_group(
    connection: AsyncConnection, queue: "JobQueue", root: dict, row: dict, counts: dict
) -> None:
    summary = "、".join(f"{name}={count}" for name, count in counts.items())
    message = f"并行子任务未满足完成条件，各状态数量：{summary}"
    now = business_now()
    await connection.execute(
        update(stages)
        .where(stages.c.id == row["id"])
        .values(state="failed", error=message, finished_at=now)
    )
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(state="failed", reason=message, finished_at=now, updated_at=now)
    )
    await queue.pipelines.next_cycle(connection, root)
