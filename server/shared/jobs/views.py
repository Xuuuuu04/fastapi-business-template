"""
任务的查询和人工处理：查看任务、按状态列出、人工重新排队、取消尚未执行的任务。
查询供接口和命令行使用；人工处理只通过命令行进行，不放进只读的排查接口。
"""

import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import RowMapping, func, select, update

from shared.db.database import Database
from shared.errors.framework import QueueFull
from shared.jobs.queue import READY, release, reserve
from shared.jobs.tables import checkpoints, jobs
from shared.modules.catalog import Catalog
from shared.pipelines.storage import stage_for

STATE_TEXT = {
    "queued": "等待执行",
    "running": "执行中",
    "waiting_retry": "等待重试",
    "done": "已完成",
    "failed": "失败",
    "unknown": "结果待确认",
    "blocked": "等待兼容版本",
    "cancelled": "已取消",
}


# 供接口或命令行返回的任务状态、执行时间和运行编号。
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


# 把数据库行整理成任务视图。
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
    )


# 按编号读取一个任务。
async def get_job(database: Database, job_id: str) -> JobView | None:
    async with database.read() as connection:
        row = (await connection.execute(select(jobs).where(jobs.c.id == job_id))).mappings().first()
    return view_of(row) if row else None


# 按状态和操作列出最近的任务。
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


# 统计各状态的任务数量。
async def count_jobs(database: Database) -> dict[str, int]:
    query = select(jobs.c.state, func.count()).group_by(jobs.c.state)
    async with database.read() as connection:
        rows = (await connection.execute(query)).all()
    return {str(state): int(count) for state, count in rows}


# 人工把失败、待检查或等待兼容版本的任务重新排队；accept_version 表示接受按当前版本执行。
async def requeue(
    database: Database, catalog: Catalog, job_id: str, *, accept_version: bool
) -> str:
    async with database.write() as connection:
        stage = await stage_for(connection, job_id)
        if stage is not None:
            return f"流程阶段请用pipelines resume {stage['pipeline_id']}恢复"
        row = (await connection.execute(select(jobs).where(jobs.c.id == job_id))).mappings().first()
        if row is None:
            return "任务不存在"
        if row["state"] not in ("failed", "unknown", "blocked"):
            state = STATE_TEXT.get(row["state"])
            return f"任务状态是“{state}”；只有失败、待检查、等待兼容版本的任务可以重新排队"
        binding, plan = catalog.find(row["contract"]), catalog.plan(row["contract"])
        if binding is None or plan is None:
            return "任务对应的操作当前没有登记"
        values: dict[str, Any] = {
            "state": "queued",
            "run_after": time.time(),
            "updated_at": time.time(),
        }
        values |= {"finished_at": None, "error_code": "", "error_message": ""}
        if row["state"] == "blocked":
            if not accept_version:
                return "任务等待兼容版本；确认可以按当前版本执行时，加上 --accept-version"
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


# 取消尚未开始执行的任务。
async def cancel(database: Database, job_id: str) -> str:
    async with database.write() as connection:
        if await stage_for(connection, job_id) is not None:
            return "不能单独取消流程阶段任务"
        change = (
            update(jobs)
            .where(jobs.c.id == job_id, jobs.c.state.in_(READY))
            .values(state="cancelled", finished_at=time.time(), updated_at=time.time())
            .returning(jobs.c.contract)
        )
        name = (await connection.execute(change)).scalar()
        if name is None:
            return "只能取消等待执行或等待重试的任务"
        await release(connection, name)
    return "已取消"
