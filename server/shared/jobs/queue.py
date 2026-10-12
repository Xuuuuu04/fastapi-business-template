"""
任务表的读写：登记、领取、完成、失败、延长期限和期限过期后的处理。
登记与业务写入同事务提交，领取使用 FOR UPDATE SKIP LOCKED；排队计数原子更新。
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.db.database import Database
from shared.errors.framework import StepRuleBroken
from shared.jobs import resources
from shared.jobs.checkpoint_store import (
    create_checkpoint,
    extend_lease,
    protect_failure,
)
from shared.jobs.constraints import take
from shared.jobs.expiry import expire
from shared.jobs.submission import job_row, release, reserve, same_key, scope_for
from shared.jobs.tables import jobs
from shared.modules.catalog import Catalog
from shared.modules.contract import Contract
from shared.pipelines.engine import PipelineEngine
from shared.pipelines.failure import failed as pipeline_failed
from shared.pipelines.storage import is_pipeline_job
from shared.timing.clock import Clock, RealClock
from shared.timing.current import clocked
from shared.timing.current import now as business_now

READY = ("queued", "waiting_retry")
ACTIVE = ("queued", "running", "waiting_retry")


# 后台进程取到的任务信息，包含本次尝试编号和输入。
@dataclass(frozen=True)
class Ticket:
    id: str
    contract: str
    attempt: int
    module_version: str
    input_json: str
    caller_json: str
    request_id: str
    key: str | None = None
    failed_attempts: int | None = 0


# 通过数据库登记、领取和更新任务，保证状态变化有明确条件。
class JobQueue:
    # 使用模块目录查找任务声明，使用数据库保存任务。
    def __init__(self, catalog: Catalog, database: Database) -> None:
        self.clock: Clock = RealClock()

        self.catalog, self.database = catalog, database
        self.pipelines, self.capacity_enabled = PipelineEngine(self), False

    # 在给定的写入事务中登记任务；同一请求编号重复登记时返回原任务。
    @clocked
    async def submit(
        self,
        connection: AsyncConnection,
        item: Contract[Any, Any],
        input: Data,
        caller: Caller,
        *,
        key: str,
        request_id: str,
    ) -> str:
        if item.name in self.catalog.pipeline_starts:
            return await self.pipelines.submit(connection, item, input, caller)
        plan = self.catalog.plan(item.name)
        if plan is None:
            raise StepRuleBroken(f"操作 {item.name} 没有在模块的 jobs 中声明，不能作为任务登记")
        body, digest, key = plan.submission(input, key)
        if key:
            existing = await same_key(connection, item.name, scope_for(caller), key, digest, caller)
            if existing:
                return existing
        now = business_now()
        row = await job_row(
            connection,
            plan,
            input,
            caller,
            body,
            digest,
            key,
            self.catalog.binding(item).module.version,
            request_id,
            now,
        )
        try:
            async with connection.begin_nested():
                await reserve(connection, item, plan.max_queued)
                await connection.execute(insert(jobs).values(**row))
                if plan.segmented:
                    await create_checkpoint(connection, str(row["id"]))
        except IntegrityError:
            existing = await same_key(connection, item.name, scope_for(caller), key, digest, caller)
            if existing:
                return existing
            raise
        return str(row["id"])

    # 领取一个到期的任务，写入新的尝试编号和执行期限。
    @clocked
    async def claim(self, now: float) -> Ticket | None:
        async with self.database.write() as connection:
            row = await take(self, connection, now)
        return Ticket(**row) if row else None

    # 在给定事务中把任务标为完成；尝试已过期时返回 False，调用方应放弃本次写入。
    @clocked
    async def finish(
        self, connection: AsyncConnection, ticket: Ticket, result_json: str, run_id: str
    ) -> bool:
        now = business_now()
        change = (
            update(jobs)
            .where(
                jobs.c.id == ticket.id, jobs.c.attempt == ticket.attempt, jobs.c.state == "running"
            )
            .values(
                state="done",
                result_json=result_json,
                finished_at=now,
                updated_at=now,
                lease_until=None,
                last_run_id=run_id,
                error_code="",
                error_message="",
            )
        )
        plan = self.catalog.plan(ticket.contract)
        if plan is not None and (plan.serial or plan.resources):
            change = change.where(jobs.c.lease_until > now)
        if (await connection.execute(change)).rowcount != 1:
            return False
        await release(connection, ticket.contract)
        await resources.release(connection, ticket.id, ticket.attempt, now)
        return True

    # 记录一次失败：进入等待重试、失败、结果待确认或等待兼容版本。
    @clocked
    async def fail(
        self,
        ticket: Ticket,
        state: str,
        code: str,
        message: str,
        *,
        run_after: float = 0.0,
        run_id: str = "",
        deferred: bool = False,
    ) -> bool:
        now = business_now()
        values: dict[str, Any] = {"state": state, "updated_at": now, "lease_until": None}
        if not deferred:
            values["failed_attempts"] = (
                func.coalesce(jobs.c.failed_attempts, jobs.c.attempt - 1) + 1
            )
        values |= {"error_code": code, "error_message": message[:1000], "last_run_id": run_id}
        if state in READY:
            values["run_after"] = run_after or now
        else:
            values["finished_at"] = now
        async with self.database.write() as connection:
            plan = self.catalog.plan(ticket.contract)
            if plan is not None and plan.segmented:
                state = await protect_failure(connection, ticket.id, state, values)
            change = (
                update(jobs)
                .where(
                    jobs.c.id == ticket.id,
                    jobs.c.attempt == ticket.attempt,
                    jobs.c.state == "running",
                )
                .values(**values)
            )
            changed = (await connection.execute(change)).rowcount == 1
            if changed:
                await resources.release(connection, ticket.id, ticket.attempt, now)
            if changed and state not in ACTIVE:
                await release(connection, ticket.contract)
            if changed and is_pipeline_job(ticket):
                await pipeline_failed(
                    connection, self, ticket.id, state, str(values["error_message"]), run_id
                )
        return changed

    # 延长执行期限；返回 False 表示任务已不属于这次尝试。
    @clocked
    async def extend(self, ticket: Ticket, until: float, *, require_current: bool = False) -> bool:
        plan = self.catalog.plan(ticket.contract)
        require_current = require_current or bool(plan and (plan.serial or plan.resources))
        return await extend_lease(self.database, ticket, until, require_current=require_current)

    # 处理执行期限已过的任务：可安全重复的重新排队，其他的标为结果待确认。
    @clocked
    async def reclaim(self, now: float) -> int:
        async with self.database.write() as connection:
            expired = (
                select(jobs.c.id, jobs.c.contract, jobs.c.attempt, jobs.c.key)
                .where(jobs.c.state == "running", jobs.c.lease_until < now)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            rows = (await connection.execute(expired)).all()
            for row in rows:
                await expire(
                    connection,
                    self.catalog,
                    row.id,
                    row.contract,
                    row.attempt,
                    now,
                    bool(row.key and row.key.startswith("pipeline:")),
                )
                if row.key and row.key.startswith("pipeline:"):
                    state = await connection.scalar(select(jobs.c.state).where(jobs.c.id == row.id))
                    await pipeline_failed(connection, self, row.id, str(state), "任务租约已过期")
        return len(rows)


# 任务领取后需要的列。
def ticket_columns() -> list[Any]:
    names = (
        "id",
        "contract",
        "attempt",
        "module_version",
        "input_json",
        "caller_json",
        "request_id",
        "key",
        "failed_attempts",
    )
    return [jobs.c[name] for name in names]


# 把调用者转成可保存的 JSON 文本。
def caller_text(caller: Caller) -> str:
    return json.dumps(caller.to_record(), ensure_ascii=False)
