"""
任务表的读写：登记、领取、完成、失败、延长期限和期限过期后的处理。
登记与业务写入同事务提交，领取使用 FOR UPDATE SKIP LOCKED；排队计数原子更新。
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.db.database import Database
from shared.errors.framework import DuplicateRequest, QueueFull, StepRuleBroken
from shared.jobs.checkpoint_store import (
    create_checkpoint,
    extend_lease,
    protect_failure,
)
from shared.jobs.expiry import expire
from shared.jobs.tables import job_counts, jobs
from shared.modules.catalog import Catalog
from shared.modules.contract import Contract
from shared.operations.capacity import capacity_filter
from shared.pipelines.engine import PipelineEngine
from shared.pipelines.failure import failed as pipeline_failed
from shared.pipelines.storage import is_pipeline_job

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


# 通过数据库登记、领取和更新任务，保证状态变化有明确条件。
class JobQueue:
    # 使用模块目录查找任务声明，使用数据库保存任务。
    def __init__(self, catalog: Catalog, database: Database) -> None:
        self.catalog, self.database = catalog, database
        self.pipelines, self.capacity_enabled = PipelineEngine(self), False

    # 在给定的写入事务中登记任务；同一请求编号重复登记时返回原任务。
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
        body = input.model_dump_json()
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if key:
            existing = await same_key(connection, item.name, caller.id, key, digest)
            if existing:
                return existing
        now = time.time()
        row = {
            "id": secrets.token_hex(8),
            "contract": item.name,
            "module_version": self.catalog.binding(item).module.version,
            "state": "queued",
            "input_json": body,
            "input_hash": digest,
            "caller_json": caller_text(caller),
            "key_scope": caller.id if key else "",
            "key": key or None,
            "attempt": 0,
            "run_after": now,
            "created_at": now,
            "updated_at": now,
            "request_id": request_id,
        }
        try:
            async with connection.begin_nested():
                await reserve(connection, item, plan.max_queued)
                await connection.execute(insert(jobs).values(**row))
                if plan.segmented:
                    await create_checkpoint(connection, str(row["id"]))
        except IntegrityError:
            existing = await same_key(connection, item.name, caller.id, key, digest)
            if existing:
                return existing
            raise
        return str(row["id"])

    # 领取一个到期的任务，写入新的尝试编号和执行期限。
    async def claim(self, now: float) -> Ticket | None:
        async with self.database.write() as connection:
            pick = (
                select(jobs.c.id, jobs.c.contract)
                .where(jobs.c.state.in_(READY), jobs.c.run_after <= now)
                .order_by(jobs.c.run_after, jobs.c.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            pick = await capacity_filter(self, connection, pick)
            found = (await connection.execute(pick)).first()
            if found is None:
                return None
            plan = self.catalog.plan(found.contract)
            lease = plan.lease_seconds if plan else 60.0
            change = (
                update(jobs)
                .where(jobs.c.id == found.id, jobs.c.state.in_(READY))
                .values(
                    state="running",
                    attempt=jobs.c.attempt + 1,
                    lease_until=now + lease,
                    updated_at=now,
                )
                .returning(*ticket_columns())
            )
            row = (await connection.execute(change)).mappings().first()
        return Ticket(**row) if row else None

    # 在给定事务中把任务标为完成；尝试已过期时返回 False，调用方应放弃本次写入。
    async def finish(
        self, connection: AsyncConnection, ticket: Ticket, result_json: str, run_id: str
    ) -> bool:
        now = time.time()
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
        if (await connection.execute(change)).rowcount != 1:
            return False
        await release(connection, ticket.contract)
        return True

    # 记录一次失败：进入等待重试、失败、结果待确认或等待兼容版本。
    async def fail(
        self,
        ticket: Ticket,
        state: str,
        code: str,
        message: str,
        *,
        run_after: float = 0.0,
        run_id: str = "",
    ) -> bool:
        now = time.time()
        values: dict[str, Any] = {"state": state, "updated_at": now, "lease_until": None}
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
            if changed and state not in ACTIVE:
                await release(connection, ticket.contract)
            if changed and is_pipeline_job(ticket):
                await pipeline_failed(
                    connection, self, ticket.id, state, str(values["error_message"]), run_id
                )
        return changed

    # 延长执行期限；返回 False 表示任务已不属于这次尝试。
    async def extend(self, ticket: Ticket, until: float, *, require_current: bool = False) -> bool:
        return await extend_lease(self.database, ticket, until, require_current=require_current)

    # 处理执行期限已过的任务：可安全重复的重新排队，其他的标为结果待确认。
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


# 按请求编号查找已有任务；内容不同则报冲突。
async def same_key(
    connection: AsyncConnection, name: str, scope: str, key: str, digest: str
) -> str:
    query = select(jobs.c.id, jobs.c.input_hash).where(
        jobs.c.contract == name, jobs.c.key_scope == scope, jobs.c.key == key
    )
    found = (await connection.execute(query)).first()
    if found is None:
        return ""
    if found.input_hash != digest:
        raise DuplicateRequest(f"请求编号 {key} 已用于内容不同的任务 {found.id}")
    return str(found.id)


# 占用一个排队名额；已满时报错。
async def reserve(connection: AsyncConnection, item: Contract[Any, Any], limit: int) -> None:
    counts = job_counts.c
    change = (
        update(job_counts)
        .where(counts.contract == item.name, counts.active < limit)
        .values(active=counts.active + 1)
    )
    if (await connection.execute(change)).rowcount == 1:
        return
    exists = await connection.scalar(select(counts.active).where(counts.contract == item.name))
    if exists is None and limit > 0:
        try:
            async with connection.begin_nested():
                await connection.execute(insert(job_counts).values(contract=item.name, active=1))
            return
        except IntegrityError:
            if (await connection.execute(change)).rowcount == 1:
                return
    raise QueueFull(f"“{item.title}”排队已满（上限 {limit}），请稍后再试")


# 释放一个排队名额。
async def release(connection: AsyncConnection, name: str) -> None:
    counts = job_counts.c
    lowered = case((counts.active > 0, counts.active - 1), else_=0)
    await connection.execute(
        update(job_counts).where(counts.contract == name).values(active=lowered)
    )


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
    )
    return [jobs.c[name] for name in names]


# 把调用者转成可保存的 JSON 文本。
def caller_text(caller: Caller) -> str:
    return json.dumps(caller.to_record(), ensure_ascii=False)
