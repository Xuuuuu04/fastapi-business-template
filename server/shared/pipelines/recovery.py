"""
人工从当前失败阶段恢复；保留成功阶段与分段游标，未知外部结果必须另行明确确认。
"""

import json
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError
from sqlalchemy import RowMapping, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.db.database import Database
from shared.errors.framework import InvalidInput
from shared.jobs.tables import checkpoints, jobs
from shared.pipelines.queued import resume_queued
from shared.pipelines.schema import declarations
from shared.pipelines.storage import ACTIVE, compatible, root_for
from shared.pipelines.tables import runs, stages

if TYPE_CHECKING:
    from shared.modules.catalog import Catalog


# 只接受当前失败阶段；版本变化需显式确认，未知外部结果默认不能重新执行。
async def resume(
    database: Database,
    catalog: "Catalog",
    run_id: str,
    *,
    accept_schema: bool = False,
    confirm_unknown: bool = False,
) -> str:
    async with database.write() as connection:
        stage = (
            (
                await connection.execute(
                    select(stages)
                    .where(stages.c.pipeline_id == run_id)
                    .order_by(stages.c.position.desc())
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        if stage is None:
            return await resume_queued(connection, database, catalog, run_id, accept_schema)
        job = (
            (
                await connection.execute(
                    select(jobs).where(jobs.c.id == stage["job_id"]).with_for_update()
                )
            )
            .mappings()
            .one()
        )
        root = await root_for(connection, run_id)
        current = await verify(connection, catalog, root, accept_schema, confirm_unknown)
        await requeue_stage(connection, catalog, root, stage, job, current, confirm_unknown)
    return "已从当前阶段重新排队"


# 恢复前核对格式、外部确认与同组织活动周期。
async def verify(
    connection: AsyncConnection,
    catalog: "Catalog",
    root: dict,
    accept_schema: bool,
    confirm_unknown: bool,
) -> list[dict[str, str]]:
    run_id = root["id"]
    if root["state"] not in ("failed", "version_blocked", "unknown"):
        raise InvalidInput("只有失败、版本暂停、结果待确认的流程可以恢复")
    if root["state"] == "unknown" and not confirm_unknown:
        raise InvalidInput("外部结果待确认；确认未产生效果后才可显式重新执行")
    pipeline = catalog.pipelines.get(root["pipeline"])
    if pipeline is None:
        raise InvalidInput("流程当前没有登记")
    current = declarations(pipeline, catalog)
    if not compatible(root, current) and not accept_schema:
        raise InvalidInput("后续阶段声明已变化，请审查后明确接受当前格式")
    other = await connection.scalar(
        select(runs.c.id).where(
            runs.c.pipeline == root["pipeline"],
            runs.c.org_id == root["org_id"],
            runs.c.id != run_id,
            runs.c.state.in_(ACTIVE),
        )
    )
    if other:
        raise InvalidInput(f"组织的另一周期{other}尚未结束")
    return current


# 保留已有任务与游标，只重新占用当前失败阶段的队列名额。
async def requeue_stage(
    connection: AsyncConnection,
    catalog: "Catalog",
    root: dict,
    stage: RowMapping,
    job: RowMapping,
    current: list[dict[str, str]],
    confirm_unknown: bool,
) -> None:
    from shared.jobs.queue import reserve

    binding, plan = catalog.find(job["contract"]), catalog.plan(job["contract"])
    if binding is None or plan is None:
        raise InvalidInput("失败阶段操作当前没有登记")
    current_stage = next(
        (s for s in catalog.pipelines[root["pipeline"]].stages if s.name == root["current_stage"]),
        None,
    )
    if current_stage is None or current_stage.operation.name != job["contract"]:
        raise InvalidInput("阶段操作名称变化，需要迁移当前任务后恢复")
    validate_saved(binding.contract.input, job["input_json"], stage["name"])
    cursor = await connection.scalar(
        select(checkpoints.c.cursor_json).where(checkpoints.c.job_id == job["id"])
    )
    if cursor and plan.cursor:
        validate_saved(plan.cursor, cursor, stage["name"] + "游标")
    await reserve(connection, binding.contract, plan.max_queued)
    now = time.time()
    await connection.execute(
        update(jobs)
        .where(jobs.c.id == job["id"])
        .values(
            state="queued",
            run_after=now,
            finished_at=None,
            lease_until=None,
            module_version=binding.module.version,
            updated_at=now,
            error_code="",
            error_message="",
        )
    )
    await reset_stage(connection, root, stage, current, now)
    if confirm_unknown:
        await connection.execute(
            update(checkpoints)
            .where(checkpoints.c.job_id == job["id"])
            .values(external_pending=False)
        )


# 当前阶段恢复时间与流程状态和任务重新排队同事务保存。
async def reset_stage(
    connection: AsyncConnection,
    root: dict,
    stage: RowMapping,
    current: list[dict[str, str]],
    now: float,
) -> None:
    run_id = root["id"]
    await connection.execute(
        update(stages)
        .where(stages.c.id == stage["id"])
        .values(state="queued", error="", finished_at=None, wait_until=None)
    )
    await connection.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .values(
            state="running",
            reason="人工恢复当前阶段",
            declarations_json=json.dumps(current),
            updated_at=now,
            finished_at=None,
        )
    )


# 明确指出恢复中不兼容的数据位置，不把类型错误当作服务器未知故障。
def validate_saved(model: type[Data], value: str, stage: str) -> None:
    try:
        model.model_validate_json(value)
    except ValidationError as error:
        raise InvalidInput(f"流程阶段{stage}的已保存数据与当前格式不符，需要迁移后恢复") from error
