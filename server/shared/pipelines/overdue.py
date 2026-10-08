"""
逾期只记录事实并登记通知，默认继续；显式pause在批次/阶段边界停止，通知未送达保持待发送。
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import InvalidInput
from shared.pipelines.plan import Pipeline, StartRequest
from shared.pipelines.storage import root_for
from shared.pipelines.tables import notifications, runs

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue


# 截止时间在登记周期时固定，声明调整不会偷偷改正在运行的期限。
def deadline(pipeline: Pipeline, request: StartRequest, now: float) -> float | None:
    if pipeline.complete_by is None:
        return None
    point = pipeline.complete_by
    period = request.period or datetime.fromtimestamp(now, UTC)
    if period.tzinfo is None:
        raise InvalidInput(f"流程{pipeline.name}的周期时间需要时区以计算complete_by")
    zone = ZoneInfo(point.zone)
    day = period.astimezone(zone).date() + timedelta(days=point.days_after)
    return datetime.combine(day, point.at, zone).timestamp()


# 一次最多处理100个逾期周期，各自短事务，已登记通知不重复。
async def check(queue: "JobQueue", now: float) -> None:
    if not queue.catalog.pipelines:
        return
    async with queue.database.read() as connection:
        ids = (
            (
                await connection.execute(
                    select(runs.c.id)
                    .where(
                        runs.c.overdue.is_(False),
                        runs.c.complete_by.is_not(None),
                        runs.c.complete_by < now,
                        runs.c.state.not_in(("succeeded", "skipped", "cancelled")),
                    )
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
    for run_id in ids:
        async with queue.database.write() as connection:
            root = await root_for(connection, run_id)
            if root["overdue"] or root["state"] in ("succeeded", "skipped", "cancelled"):
                continue
            await mark(connection, root, now)


# 逾期标记和通知登记同事务；继续策略不修改原业务状态。
async def mark(connection: AsyncConnection, root: dict, now: float) -> None:
    values: dict[str, Any] = dict(overdue=True, overdue_at=now, updated_at=now)
    if root["on_overdue"] == "pause" and root["state"] in (
        "running",
        "waiting_external",
        "waiting_members",
        "queued",
    ):
        values["state"] = "overdue_paused"
        values["reason"] = "已逾期，按声明在批次/阶段边界暂停，等待人工继续"
    await connection.execute(update(runs).where(runs.c.id == root["id"]).values(**values))
    payload = dict(
        pipeline_id=root["id"],
        pipeline=root["pipeline"],
        org_id=root["org_id"],
        cycle_key=root["cycle_key"],
        complete_by=root["complete_by"],
        overdue_at=now,
        current_stage=root["current_stage"],
        action=root["on_overdue"],
    )
    await connection.execute(
        insert(notifications).values(
            id=secrets.token_hex(8),
            org_id=root["org_id"],
            kind="pipeline_overdue",
            key=root["id"],
            payload_json=json.dumps(payload),
            state="pending",
            created_at=now,
            attempt=0,
            error="",
        )
    )


# 分段任务每批提交后再查询；暂停不会打断本批，也不会改变普通任务行为。
async def may_continue(queue: "JobQueue", job_id: str) -> bool:
    from shared.pipelines.member_store import member_for
    from shared.pipelines.storage import stage_for

    if not queue.catalog.pipelines:
        return True
    async with queue.database.read() as connection:
        row = await stage_for(connection, job_id) or await member_for(connection, job_id)
        if row is None:
            return True
        state = await connection.scalar(select(runs.c.state).where(runs.c.id == row["pipeline_id"]))
    return state != "overdue_paused"
