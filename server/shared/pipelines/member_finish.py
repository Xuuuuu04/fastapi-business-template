"""
成员阶段结果与下一子阶段同事务提交，汇合后不再启动未纳入的新动作。
"""

import json
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import InvalidInput, StaleAttempt
from shared.jobs.tables import jobs
from shared.pipelines.member_pool import advance
from shared.pipelines.plan import FanOut, Stage, Wait
from shared.pipelines.schema import data_json
from shared.pipelines.tables import members
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue, Ticket


# 同一成员每个子阶段独立事务，等待结果不占一个长事务。
async def finish(
    connection: AsyncConnection,
    queue: "JobQueue",
    ticket: "Ticket",
    root: dict,
    parent: dict,
    member: dict,
    group: FanOut,
    stage: Stage,
    body: str,
    run_id: str,
) -> None:
    now = business_now()
    joining = parent["state"] == "joining"
    if isinstance(stage, Wait) and now >= member["wait_until"]:
        raise InvalidInput(f"成员{member['key']}阶段{stage.name}等待超时")
    value = stage.operation.output.model_validate_json(body)
    if isinstance(stage, Wait) and not getattr(value, stage.ready_field) and not joining:
        await wait_again(connection, ticket, member, stage, body, run_id, now)
        return
    if not await queue.finish(connection, ticket, body, run_id):
        raise StaleAttempt()
    await save_result(connection, member, group, stage, body, run_id, now, joining, ticket.id)
    await advance(connection, queue, root, parent, group)


# 成功产出、已完成子阶段和下一子阶段输入作为同一份成员进度保存。
async def save_result(
    connection: AsyncConnection,
    member: dict,
    group: FanOut,
    stage: Stage,
    body: str,
    run_id: str,
    now: float,
    joining: bool,
    job_id: str,
) -> None:
    history = json.loads(member["history_json"])
    history.append(
        dict(
            name=stage.name,
            job_id=job_id,
            run_id=run_id,
            output=body,
            module_version=member["module_version"],
        )
    )
    index = next(i for i, child in enumerate(group.stages) if child.name == stage.name)
    values = dict(
        output_json=body,
        run_id=run_id,
        history_json=json.dumps(history),
        error="",
        elapsed_ms=members.c.elapsed_ms + (now - member["started_at"]) * 1000,
        updated_at=now,
        finished_at=now,
    )
    if index + 1 == len(group.stages):
        values["state"] = "succeeded"
    elif joining:
        values["state"] = "skipped"
    else:
        next_stage = group.stages[index + 1]
        incoming = next_input(next_stage, member, history, body)
        values |= dict(
            state="planned",
            position=index + 1,
            phase_name=next_stage.name,
            current_input_json=incoming,
            job_id=None,
            wait_until=None,
            started_at=None,
            finished_at=None,
        )
    await connection.execute(update(members).where(members.c.id == member["id"]).values(**values))


# 显式输入来源只能是原始成员Data或已成功子阶段。
def next_input(stage: Stage, member: dict, history: list[dict], previous: str) -> str:
    if stage.input_from == "previous":
        body = previous
    elif stage.input_from == "input":
        body = member["input_json"]
    else:
        body = next(item["output"] for item in history if item["name"] == stage.input_from)
    data = stage.operation.input.model_validate_json(body)
    return data_json(stage.operation.input, data, member["key"] + "/" + stage.name)


# 等待每次只做一个检查，同一任务按间隔重新领取，保留原截止时间。
async def wait_again(
    connection: AsyncConnection,
    ticket: "Ticket",
    member: dict,
    stage: Wait,
    body: str,
    run_id: str,
    now: float,
) -> None:
    await connection.execute(
        update(jobs)
        .where(jobs.c.id == ticket.id)
        .values(
            state="waiting_retry",
            lease_until=None,
            run_after=min(now + stage.every, member["wait_until"]),
            last_run_id=run_id,
            result_json=body,
            updated_at=now,
        )
    )
    await connection.execute(
        update(members)
        .where(members.c.id == member["id"])
        .values(
            state="waiting_external",
            output_json=body,
            run_id=run_id,
            elapsed_ms=members.c.elapsed_ms + (now - member["started_at"]) * 1000,
            updated_at=now,
        )
    )
