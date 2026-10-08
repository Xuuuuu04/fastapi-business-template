"""
扇出池：规划和派发分离，只登记有限在途成员，队列满时保存等待并由worker重新检查。
"""

import json
import time
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import caller_from_record
from shared.errors.framework import InvalidInput, QueueFull
from shared.jobs.tables import jobs
from shared.pipelines.member_compat import block, group_compatible, member_compatible
from shared.pipelines.plan import All, FanOut, Pipeline, Ratio, Wait
from shared.pipelines.tables import members, runs, stages

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue

BUSY = ("queued", "running", "waiting_retry")


# 规划产出已提交前，成员仍只是计划；规划成功与池启用使用同一事务。
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
            raise InvalidInput(f"扇出阶段{group.name}缺少Ratio声明的必需成员")
    await connection.execute(
        update(stages)
        .where(stages.c.id == row["id"])
        .values(state="waiting_members", output_json=body, run_id=run_id, error="")
    )
    await connection.execute(
        update(runs)
        .where(runs.c.id == root["id"])
        .values(state="waiting_members", updated_at=time.time(), reason="")
    )
    row.update(state="waiting_members", output_json=body, run_id=run_id)
    root["state"] = "waiting_members"
    await advance(connection, queue, root, row, group)


# 成员或维护器触发同一推进逻辑，不在内存里保留协调状态。
async def advance(
    connection: AsyncConnection, queue: "JobQueue", root: dict, row: dict, group: FanOut
) -> None:
    if root["state"] not in ("waiting_members", "running"):
        return
    pipeline = queue.catalog.pipelines[root["pipeline"]]
    if not group_compatible(root, group, pipeline, queue.catalog):
        await block(connection, root, row, "扇出汇合声明或后续阶段格式变化")
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


# 汇合分母始终是本次规划的全部成员，必需成员不能被比例忽略。
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


# 达标瞬间冻结本次纳入清单，不再派发新成员，迟到结果只留记录。
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
        .values(state="skipped", updated_at=time.time(), finished_at=time.time())
    )
    await connection.execute(update(stages).where(stages.c.id == stage_id).values(state="joining"))


# 只有有限数量的成员拥有排队或运行的任务，等待检查也占成员名额。
async def active_count(connection: AsyncConnection, stage_id: str) -> int:
    result = await connection.scalar(
        select(func.count())
        .select_from(members.join(jobs, members.c.job_id == jobs.c.id))
        .where(members.c.stage_id == stage_id, jobs.c.state.in_(BUSY))
    )
    return int(result or 0)


# 状态只取计数，协调器不把数百个成员正文加载进内存。
async def states_of(connection: AsyncConnection, stage_id: str) -> dict[str, int]:
    rows = await connection.execute(
        select(members.c.state, func.count())
        .where(members.c.stage_id == stage_id)
        .group_by(members.c.state)
    )
    return {state: int(count) for state, count in rows}


# 逐个派发空位，单一合同的队列满时仍保留已规划成员，不使规划阶段失败。
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
                f"成员{member['key']}阶段{member['phase_name']}或后续格式变化",
            )
            return
        try:
            async with connection.begin_nested():
                await dispatch(connection, queue, root, group, dict(member))
        except QueueFull:
            await connection.execute(
                update(runs)
                .where(runs.c.id == root["id"])
                .values(reason="成员任务队列已满，等待空位", updated_at=time.time())
            )
            break


# 新阶段新建任务；失败当前阶段则复用任务及PR1已提交游标。
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
                run_after=time.time(),
                lease_until=None,
                finished_at=None,
                updated_at=time.time(),
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
            updated_at=time.time(),
            wait_until=(member["wait_until"] or time.time() + stage.timeout)
            if isinstance(stage, Wait)
            else None,
        )
    )


# 所有活跃成员已收尾后才进入下一阶段；规划产出是有界引用而非整份成员结果。
async def completed(
    connection: AsyncConnection, queue: "JobQueue", root: dict, row: dict, group: FanOut
) -> None:
    pipeline: Pipeline = queue.catalog.pipelines[root["pipeline"]]
    index = next(i for i, stage in enumerate(pipeline.stages) if stage.name == group.name)
    now = time.time()
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


# 所有成员已完成仍未达标才宣布失败，成功结果保留供失败成员恢复复用。
async def failed_group(
    connection: AsyncConnection, queue: "JobQueue", root: dict, row: dict, counts: dict
) -> None:
    message = f"扇出成员未达到汇合要求：{counts}"
    now = time.time()
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
