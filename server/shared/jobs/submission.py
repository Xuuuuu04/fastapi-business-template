"""
任务提交的去重与排队计数，跨事务共享的名额由条件更新维护。
"""

import hashlib
import json
import secrets
from typing import Any

from sqlalchemy import case, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller, caller_from_record
from shared.data.models import Data
from shared.errors.framework import DuplicateRequest, QueueFull, StepRuleBroken
from shared.jobs import resources
from shared.jobs.limits import submission_limits
from shared.jobs.plan import JobPlan
from shared.jobs.tables import job_counts, jobs
from shared.modules.contract import Contract


# 按请求编号查找已有任务；内容不同则报冲突。
async def same_key(
    connection: AsyncConnection,
    name: str,
    scope: str,
    key: str,
    digest: str,
    caller: Caller | None = None,
) -> str:
    scopes = (scope, caller.id) if caller else (scope,)
    query = select(jobs.c.id, jobs.c.input_hash, jobs.c.caller_json).where(
        jobs.c.contract == name, jobs.c.key_scope.in_(scopes), jobs.c.key == key
    )
    rows = (await connection.execute(query)).all()
    matches = [row for row in rows if caller is None or matching_scope(row.caller_json, caller)]
    if len(matches) > 1:
        raise StepRuleBroken("同一业务键有多份身份相符的历史任务，需要先核对原任务")
    if matches and matches[0].input_hash != digest:
        raise DuplicateRequest(f"请求编号 {key} 已用于内容不同的任务 {matches[0].id}")
    return str(matches[0].id) if matches else ""


# 新键包括组织与身份类型；旧键仍核对冻结身份，避免升级后重复未知任务。
def scope_for(caller: Caller) -> str:
    body = json.dumps([caller.kind, caller.id, caller.org_id])
    return hashlib.sha256(body.encode()).hexdigest()


# 旧身份缺失或损坏时不猜组织，不通过新登记覆盖不明确的历史。
def matching_scope(body: str, caller: Caller) -> bool:
    try:
        raw = json.loads(body)
    except ValueError:
        raise StepRuleBroken("历史任务身份损坏，需要先查证") from None
    if not isinstance(raw, dict) or not {"org_id", "kind", "id"} <= set(raw):
        raise StepRuleBroken("历史任务身份不完整，需要先查证")
    return scope_for(caller_from_record(raw)) == scope_for(caller)


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


# 输入、身份、业务约束和串行顺序作为同一份冻结登记保存。
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
