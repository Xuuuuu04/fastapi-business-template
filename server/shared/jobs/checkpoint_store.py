"""
分段恢复位置、外部写入意图与已提交段的持久化。
段结果与业务写入共用事务；提交前锁住并核对任务尝试和租约，旧尝试全部回滚。
"""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.database import Database
from shared.errors.framework import RemoteResultUnknown, StaleAttempt, StepRuleBroken
from shared.jobs import resources
from shared.jobs.checkpoint import Checkpoint
from shared.jobs.plan import JobPlan
from shared.jobs.tables import checkpoints, jobs, segments
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import Ticket


# 取得上一批的恢复位置；待确认的外部写入不能自动重做。
async def load(database: Database, job_id: str) -> tuple[int, dict[str, Any], int]:
    async with database.read() as connection:
        row = (
            (await connection.execute(select(checkpoints).where(checkpoints.c.job_id == job_id)))
            .mappings()
            .first()
        )
    if row is None:
        raise StepRuleBroken("分段任务缺少恢复位置，请按新模块版本重新登记")
    if row["external_pending"]:
        raise RemoteResultUnknown("上一批有外部写入待确认，请查询原结果后再人工恢复")
    return int(row["number"]), json.loads(row["cursor_json"]), int(row["total_rows"])


# 核对本次领取仍有效，并持有任务行锁直到段提交完成。
async def own(connection: AsyncConnection, ticket: "Ticket") -> None:
    now = business_now()
    changed = await connection.execute(
        update(jobs)
        .where(
            jobs.c.id == ticket.id,
            jobs.c.attempt == ticket.attempt,
            jobs.c.state == "running",
            jobs.c.lease_until > now,
        )
        .values(updated_at=now)
    )
    if changed.rowcount != 1:
        raise StaleAttempt()


# 发送外部写入之前独立提交意图，进程被强杀后也不能重新发送这一批。
async def mark_external(database: Database, ticket: "Ticket", number: int) -> None:
    async with database.write() as connection:
        await own(connection, ticket)
        changed = await connection.execute(
            update(checkpoints)
            .where(checkpoints.c.job_id == ticket.id, checkpoints.c.number == number)
            .values(external_pending=True)
        )
        if changed.rowcount != 1:
            raise StaleAttempt()


# 在业务段事务中保存游标与段证据，只有提交成功后才能进入下一段。
async def save(
    connection: AsyncConnection,
    ticket: "Ticket",
    checkpoint: Checkpoint,
    run_id: str,
    elapsed_ms: float,
) -> None:
    checkpoint.validate()
    await own(connection, ticket)
    changed = await connection.execute(
        update(checkpoints)
        .where(checkpoints.c.job_id == ticket.id, checkpoints.c.number == checkpoint.number)
        .values(
            number=checkpoint.number + 1,
            cursor_json=checkpoint.next_cursor,
            external_pending=False,
            total_rows=checkpoint.total_rows + checkpoint.rows,
        )
    )
    if changed.rowcount != 1:
        raise StaleAttempt()
    await connection.execute(
        insert(segments).values(
            job_id=ticket.id,
            number=checkpoint.number + 1,
            attempt=ticket.attempt,
            run_id=run_id,
            cursor_json=checkpoint.next_cursor,
            rows=checkpoint.rows,
            total_rows=checkpoint.total_rows + checkpoint.rows,
            elapsed_ms=elapsed_ms,
            committed_at=business_now(),
        )
    )
    await connection.execute(update(jobs).where(jobs.c.id == ticket.id).values(last_run_id=run_id))


# 判断任务是否有未确认的外部效果，领取和失败处理共用。
async def external_pending(connection: AsyncConnection, job_id: str) -> bool:
    return bool(
        await connection.scalar(
            select(checkpoints.c.external_pending).where(checkpoints.c.job_id == job_id)
        )
    )


# 仅显式分段任务初始化游标，普通任务不访问新表。
async def create_checkpoint(connection: AsyncConnection, job_id: str) -> None:
    await connection.execute(
        insert(checkpoints).values(
            job_id=job_id,
            number=0,
            cursor_json="{}",
            external_pending=False,
            total_rows=0,
        )
    )


# 有外部写入意图的故障保守保留待确认，不进入自动重试。
async def protect_failure(
    connection: AsyncConnection, job_id: str, state: str, values: dict[str, Any]
) -> str:
    if await external_pending(connection, job_id):
        values.update(
            state="unknown",
            finished_at=business_now(),
            error_code="remote_result_unknown",
            error_message="本批有外部写入待确认，请查询原结果后再人工恢复",
        )
        return "unknown"
    return state


# 分页查看已提交段，崩溃后仍能查到每段的行数和耗时。
async def list_segments(
    database: Database, job_id: str, *, after: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    async with database.read() as connection:
        rows = (
            (
                await connection.execute(
                    select(segments)
                    .where(
                        segments.c.job_id == job_id,
                        segments.c.number > after,
                    )
                    .order_by(segments.c.number)
                    .limit(limit)
                )
            )
            .mappings()
            .all()
        )
    return [{**dict(row), "cursor": json.loads(row["cursor_json"])} for row in rows]


# 租约失效只有安全且没有在途外部写入的任务可重新领取。
async def may_resume(
    connection: AsyncConnection, plan: JobPlan | None, job_id: str, attempt: int
) -> bool:
    if plan is None or not plan.repeat_safe or attempt >= max(plan.retry.times + 1, 3):
        return False
    return not (plan.segmented and await external_pending(connection, job_id))


# 任务查看的当前恢复位置与累计数据，普通任务没有分段状态。
async def progress(database: Database, job_id: str) -> dict[str, Any] | None:
    async with database.read() as connection:
        row = (
            (await connection.execute(select(checkpoints).where(checkpoints.c.job_id == job_id)))
            .mappings()
            .first()
        )
        if row is None:
            return None
        last = (
            (
                await connection.execute(
                    select(segments).where(
                        segments.c.job_id == job_id, segments.c.number == row["number"]
                    )
                )
            )
            .mappings()
            .first()
        )
    return {
        "committed_batches": row["number"],
        "cursor": json.loads(row["cursor_json"]),
        "total_rows": row["total_rows"],
        "external_pending": row["external_pending"],
        "last_batch": dict(last) if last else None,
    }


# 续租只更新仍属于本次领取的任务；分段任务额外禁止复活已过期租约。
async def extend_lease(
    database: Database, ticket: "Ticket", until: float, *, require_current: bool = False
) -> bool:
    async with database.write() as connection:
        change = (
            update(jobs)
            .where(
                jobs.c.id == ticket.id,
                jobs.c.attempt == ticket.attempt,
                jobs.c.state == "running",
            )
            .values(lease_until=until, updated_at=business_now())
        )
        if require_current:
            change = change.where(jobs.c.lease_until > business_now())
        changed = (await connection.execute(change)).rowcount == 1
        if changed:
            await resources.extend(connection, ticket.id, ticket.attempt, until)
        return changed
