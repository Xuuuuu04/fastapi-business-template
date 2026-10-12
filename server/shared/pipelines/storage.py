"""
流程持久化的共用查询与有条件状态更新，调用方明确持有当前事务。
"""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import InvalidInput, StaleAttempt
from shared.jobs.tables import jobs
from shared.pipelines.tables import runs, stages
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import Ticket

ACTIVE = (
    "running",
    "waiting_external",
    "waiting_members",
    "overdue_paused",
    "unknown",
    "version_blocked",
)
PREFIX = "pipeline:"


# 阶段任务始终使用框架专用键，普通任务不需要查询流程表。
def is_pipeline_job(ticket: "Ticket") -> bool:
    return bool(ticket.key and ticket.key.startswith(PREFIX))


# 找到实际关联的阶段，不接受仅伪造请求键的普通任务。
async def stage_for(connection: AsyncConnection, job_id: str) -> dict[str, Any] | None:
    row = (
        (await connection.execute(select(stages).where(stages.c.job_id == job_id)))
        .mappings()
        .first()
    )
    return dict(row) if row else None


# 锁定流程运行，阶段推进与恢复串行执行。
async def root_for(connection: AsyncConnection, run_id: str) -> dict[str, Any]:
    row = (
        (
            await connection.execute(
                select(runs).where(runs.c.id == run_id).with_for_update(key_share=True)
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise InvalidInput("流程运行不存在")
    return dict(row)


# 确保本次尝试未过期、未被重新领取，后续所有业务写入才可以提交。
async def own(connection: AsyncConnection, ticket: "Ticket") -> None:
    changed = await connection.execute(
        update(jobs)
        .where(
            jobs.c.id == ticket.id,
            jobs.c.attempt == ticket.attempt,
            jobs.c.state == "running",
            jobs.c.lease_until > business_now(),
        )
        .values(updated_at=business_now())
    )
    if changed.rowcount != 1:
        raise StaleAttempt()


# 只对后续阶段比较格式，内部实现和模块版本不参与兼容性判断。
def compatible(root: dict, current: list[dict[str, str]]) -> bool:
    saved = json.loads(root["declarations_json"])
    name = root["current_stage"]
    old_index = next((i for i, item in enumerate(saved) if item["name"] == name), None)
    new_index = next((i for i, item in enumerate(current) if item["name"] == name), None)
    return (
        old_index is not None and new_index is not None and saved[old_index:] == current[new_index:]
    )
