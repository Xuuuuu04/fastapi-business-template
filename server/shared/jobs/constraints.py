"""
领取前检查期限、业务键顺序和跨worker资源；等待只改下次领取时间，不开启业务执行。
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.jobs.limits import ResourceLimit
from shared.jobs.resources import acquire
from shared.jobs.submission import release
from shared.jobs.tables import jobs
from shared.operations.capacity import capacity_filter

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue


# 一次最多观察32个候选，不让一个业务键的等待让其他业务键长期无法领取。
async def take(queue: "JobQueue", connection: AsyncConnection, now: float) -> dict[str, Any] | None:
    from shared.jobs.queue import READY, ticket_columns

    await expire_ready(connection, now)
    rows = await candidates(queue, connection, now)
    for candidate in rows:
        row = await lock_candidate(connection, candidate["id"], now)
        if row is None:
            continue
        if await expired(connection, row, now) or await serial_blocked(connection, row):
            continue
        plan = queue.catalog.plan(row["contract"])
        if plan is not None and await missing_limits(connection, plan, row, now):
            continue
        lease = plan.lease_seconds if plan else 60
        resources = plan.resources if plan else ()
        if row["serial_key"]:
            resources = (*resources, ResourceLimit("serial." + row["serial_key"]))
        blocked_until = await acquire(
            connection, resources, row["id"], row["attempt"] + 1, now, now + lease
        )
        if blocked_until is not None:
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == row["id"])
                .values(run_after=max(now + 0.01, blocked_until))
            )
            continue
        result = await connection.execute(
            update(jobs)
            .where(
                jobs.c.id == row["id"], jobs.c.state.in_(READY), jobs.c.attempt == row["attempt"]
            )
            .values(
                state="running",
                attempt=jobs.c.attempt + 1,
                lease_until=now + lease,
                updated_at=now,
                failed_attempts=func.coalesce(jobs.c.failed_attempts, jobs.c.attempt),
            )
            .returning(*ticket_columns())
        )
        found = result.mappings().first()
        return dict(found) if found else None
    return None


# 过期任务从未发送，不领取业务位置，保留冻结输入和错误原因。
async def expired(connection: AsyncConnection, row: Any, now: float) -> bool:
    queue_expired = (
        row["attempt"] == 0 and row["queued_until"] is not None and row["queued_until"] <= now
    )
    valid_expired = row["valid_until"] is not None and row["valid_until"] <= now
    if not (queue_expired or valid_expired):
        return False
    await connection.execute(
        update(jobs)
        .where(jobs.c.id == row["id"])
        .values(
            state="expired",
            finished_at=now,
            updated_at=now,
            error_code="task_expired",
            error_message="排队预算耗尽" if queue_expired else "业务有效期已过",
        )
    )
    await release(connection, row["contract"])
    return True


# 未知结果保留当前键的恢复顺序，较早的等待重试也不能被较晚提交越过。
async def serial_blocked(connection: AsyncConnection, row: Any) -> bool:
    if not row["serial_key"]:
        return False
    other = (
        select(jobs.c.id)
        .where(
            jobs.c.serial_key == row["serial_key"],
            jobs.c.id != row["id"],
            or_(
                jobs.c.state == "unknown",
                (jobs.c.state.in_(("queued", "running", "waiting_retry")))
                & (jobs.c.serial_position < row["serial_position"]),
            ),
        )
        .limit(1)
    )
    return (await connection.scalar(other)) is not None


# 即使资源冷却到很晚，已经过期的任务也及时结束，不等到run_after才释放排队名额。
async def expire_ready(connection: AsyncConnection, now: float) -> None:
    pick = (
        select(jobs.c.id, jobs.c.contract, jobs.c.attempt, jobs.c.queued_until, jobs.c.valid_until)
        .where(
            jobs.c.state.in_(("queued", "waiting_retry")),
            or_((jobs.c.attempt == 0) & (jobs.c.queued_until <= now), jobs.c.valid_until <= now),
        )
        .limit(32)
        .with_for_update(skip_locked=True)
    )
    rows = (await connection.execute(pick)).mappings().all()
    for row in rows:
        await expired(connection, row, now)


# 候选只加载约束字段，实际领取后才读取完整输入，历史大正文不进入候选内存。
async def candidates(queue: "JobQueue", connection: AsyncConnection, now: float) -> list[Any]:
    from shared.jobs.queue import READY

    pick = (
        select(
            *[
                jobs.c[name]
                for name in (
                    "id",
                    "contract",
                    "attempt",
                    "serial_key",
                    "serial_position",
                    "queued_until",
                    "valid_until",
                )
            ]
        )
        .where(jobs.c.state.in_(READY), jobs.c.run_after <= now)
        .order_by(jobs.c.run_after, jobs.c.created_at, jobs.c.id)
        .limit(32)
    )
    pick = await capacity_filter(queue, connection, pick)
    return list((await connection.execute(pick)).mappings().all())


# 每次只锁一条候选，不让一个worker预先占住其他业务键的所有候选。
async def lock_candidate(connection: AsyncConnection, id: str, now: float) -> Any:
    names = (
        "id",
        "contract",
        "attempt",
        "serial_key",
        "serial_position",
        "queued_until",
        "valid_until",
    )
    pick = (
        select(*[jobs.c[name] for name in names])
        .where(
            jobs.c.id == id, jobs.c.state.in_(("queued", "waiting_retry")), jobs.c.run_after <= now
        )
        .with_for_update(skip_locked=True)
    )
    return (await connection.execute(pick)).mappings().first()


# 旧任务没有冻结新约束时保留等待处理，不能用当前规则推造旧业务事实。
async def missing_limits(connection: AsyncConnection, plan: Any, row: Any, now: float) -> bool:
    missing = bool(plan.serial and not row["serial_key"])
    missing |= bool(plan.valid_until_field and row["valid_until"] is None)
    missing |= bool(plan.queue_timeout and row["attempt"] == 0 and row["queued_until"] is None)
    if not missing:
        return False
    await connection.execute(
        update(jobs)
        .where(jobs.c.id == row["id"])
        .values(
            state="blocked",
            updated_at=now,
            finished_at=now,
            error_code="limits_changed",
            error_message="当前声明增加了旧任务未冻结的业务约束，请核对旧输入后重新登记",
        )
    )
    await release(connection, row["contract"])
    return True
