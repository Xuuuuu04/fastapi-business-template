import hashlib
import json
import secrets
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.errors.framework import DuplicateRequest, QueueFull, StepRuleBroken
from shared.flow.entry_errors import check_access
from shared.jobs import resources
from shared.jobs.limits import submission_limits
from shared.jobs.plan import JobPlan
from shared.jobs.tables import job_counts, jobs
from shared.modules.contract import Contract

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime


async def submit_entry(
    runtime: "Runtime", item: Contract, input: Data, caller: Caller, key: str, request_id: str
) -> str:
    if runtime.jobs is None:
        raise StepRuleBroken("没有启用后台任务功能")
    check_access(item, caller)
    async with runtime.database.write() as connection:
        return await runtime.jobs.submit(
            connection, item, input, caller, key=key, request_id=request_id
        )


async def same_key(
    connection: AsyncConnection, name: str, scope: str, key: str, digest: str
) -> str:
    query = select(jobs.c.id, jobs.c.input_hash).where(
        jobs.c.contract == name, jobs.c.key_scope == scope, jobs.c.key == key
    )
    row = (await connection.execute(query)).first()
    if row is not None and row.input_hash != digest:
        raise DuplicateRequest(f"请求编号 {key} 已用于内容不同的任务 {row.id}")
    return str(row.id) if row is not None else ""


def scope_for(caller: Caller) -> str:
    body = json.dumps([caller.kind, caller.id, caller.org_id])
    return hashlib.sha256(body.encode()).hexdigest()


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


async def release(connection: AsyncConnection, name: str) -> None:
    counts = job_counts.c
    lowered = case((counts.active > 0, counts.active - 1), else_=0)
    await connection.execute(
        update(job_counts).where(counts.contract == name).values(active=lowered)
    )


async def job_row(
    connection: AsyncConnection,
    plan: JobPlan,
    input: Data,
    caller: Caller,
    body: str,
    digest: str,
    key: str,
    version: str,
    request_id: str,
    now: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": secrets.token_hex(8),
        "contract": plan.contract.name,
        "module_version": version,
        "state": "queued",
        "input_json": body,
        "input_hash": digest,
        "caller_json": json.dumps(caller.to_record(), ensure_ascii=False),
        "key_scope": scope_for(caller) if key else "",
        "key": key or None,
        "attempt": 0,
        "run_after": now,
        "created_at": now,
        "updated_at": now,
        "request_id": request_id,
    }
    row.update(submission_limits(plan, input, caller, now))
    if row["serial_key"]:
        row["serial_position"] = await resources.serial_position(connection, row["serial_key"])
    return row
