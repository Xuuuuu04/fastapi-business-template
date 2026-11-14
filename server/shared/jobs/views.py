import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import RowMapping, func, select, update

from shared.db.database import Database
from shared.errors.framework import QueueFull
from shared.jobs.queue import READY, release, reserve
from shared.jobs.tables import checkpoints, jobs
from shared.modules.catalog import Catalog
from shared.pipelines.member_store import member_for
from shared.pipelines.storage import stage_for
from shared.timing.current import now as business_now

STATE_TEXT = {
    "expired": "已过期，停止执行",
    "queued": "等待执行",
    "running": "执行中",
    "waiting_retry": "等待重试",
    "done": "已完成",
    "failed": "失败",
    "unknown": "结果待确认",
    "blocked": "等待确认执行配置",
    "cancelled": "已取消",
}


@dataclass(frozen=True)
class JobView:
    id: str
    contract: str
    state: str
    state_text: str
    attempt: int
    caller_id: str
    created_at: float
    updated_at: float
    finished_at: float | None
    error_code: str
    error_message: str
    last_run_id: str
    result: Any
    caller_kind: str = ""
    org_id: str = ""


def view_of(row: RowMapping) -> JobView:
    caller = json.loads(row["caller_json"])
    return JobView(
        id=row["id"],
        contract=row["contract"],
        state=row["state"],
        state_text=STATE_TEXT.get(row["state"], row["state"]),
        attempt=row["attempt"],
        caller_id=str(caller.get("id", "")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        last_run_id=row["last_run_id"],
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        caller_kind=str(caller.get("kind", "")),
        org_id=str(caller.get("org_id", "")),
    )


async def get_job(database: Database, job_id: str) -> JobView | None:
    async with database.read() as connection:
        row = (await connection.execute(select(jobs).where(jobs.c.id == job_id))).mappings().first()
    return view_of(row) if row else None


async def list_jobs(
    database: Database, *, state: str = "", contract: str = "", limit: int = 50
) -> list[JobView]:
    query = select(jobs).order_by(jobs.c.created_at.desc()).limit(limit)
    if state:
        query = query.where(jobs.c.state == state)
    if contract:
        query = query.where(jobs.c.contract == contract)
    async with database.read() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [view_of(row) for row in rows]


async def count_jobs(database: Database) -> dict[str, int]:
    query = select(jobs.c.state, func.count()).group_by(jobs.c.state)
    async with database.read() as connection:
        rows = (await connection.execute(query)).all()
    return {str(state): int(count) for state, count in rows}


async def requeue(
    database: Database, catalog: Catalog, job_id: str, *, accept_version: bool
) -> str:
    async with database.write() as connection:
        stage = await stage_for(connection, job_id) or await member_for(connection, job_id)
        if stage is not None:
            return (
                f"这是流程阶段任务，请用 dev pipelines resume {stage['pipeline_id']} 恢复整个流程"
            )
        row = (await connection.execute(select(jobs).where(jobs.c.id == job_id))).mappings().first()
        if row is None:
            return "任务不存在"
        if row["state"] not in ("failed", "unknown", "blocked"):
            state = STATE_TEXT.get(row["state"])
            return (
                f"任务状态是“{state}”；只有执行失败、结果待确认或等待确认执行配置的任务可以重新排队"
            )
        binding, plan = catalog.find(row["contract"]), catalog.plan(row["contract"])
        if binding is None or plan is None:
            return "任务对应的操作当前没有登记"
        values: dict[str, Any] = {
            "state": "queued",
            "run_after": business_now(),
            "updated_at": business_now(),
        }
        values |= {"finished_at": None, "error_code": "", "error_message": ""}
        if row["state"] == "blocked":
            if not accept_version:
                return "任务的执行配置需要确认；确认可按当前版本执行后，加上 --accept-version"
            values["module_version"] = binding.module.version
        try:
            await reserve(connection, binding.contract, plan.max_queued)
        except QueueFull as error:
            return error.detail
        await connection.execute(update(jobs).where(jobs.c.id == job_id).values(**values))
        if plan.segmented and row["state"] == "unknown":
            await connection.execute(
                update(checkpoints)
                .where(checkpoints.c.job_id == job_id)
                .values(external_pending=False)
            )
    return "已重新排队"


async def cancel(database: Database, job_id: str) -> str:
    async with database.write() as connection:
        if (
            await stage_for(connection, job_id) is not None
            or await member_for(connection, job_id) is not None
        ):
            return "这是流程阶段任务，不能单独取消"
        change = (
            update(jobs)
            .where(jobs.c.id == job_id, jobs.c.state.in_(READY))
            .values(state="cancelled", finished_at=business_now(), updated_at=business_now())
            .returning(jobs.c.contract)
        )
        name = (await connection.execute(change)).scalar()
        if name is None:
            return "只能取消等待执行或等待重试的任务"
        await release(connection, name)
    return "已取消"
