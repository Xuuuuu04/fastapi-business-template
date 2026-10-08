"""
后台阶段执行前核对兼容性与等待容量，完成时原子提交产出并推进下一阶段。
"""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.errors.framework import InvalidInput, StaleAttempt
from shared.jobs.tables import job_counts, jobs
from shared.pipelines.plan import Pipeline, Stage, Wait
from shared.pipelines.schema import data_json, declarations
from shared.pipelines.storage import compatible, is_pipeline_job, own, root_for, stage_for
from shared.pipelines.tables import runs, stages

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue, Ticket


# 一次实际领取对应的流程与阶段，普通任务不会创建此上下文。
@dataclass
class StageContext:
    queue: "JobQueue"
    ticket: "Ticket"
    root: dict
    row: dict
    pipeline: Pipeline | None
    stage: Stage | None
    allowed: bool = True

    # 阶段产出、任务结束、下一阶段登记全部使用业务写入事务。
    async def finish(self, connection: AsyncConnection, result: Data, run_id: str) -> None:
        assert self.stage is not None and self.pipeline is not None
        body = data_json(self.stage.operation.output, result, self.stage.name)
        await own(connection, self.ticket)
        root = await root_for(connection, self.root["id"])
        if root["current_stage"] != self.stage.name or root["state"] not in (
            "running",
            "waiting_external",
        ):
            raise StaleAttempt()
        now = time.time()
        if isinstance(self.stage, Wait) and now >= self.row["wait_until"]:
            raise InvalidInput(f"流程阶段{self.stage.name}等待已超时")
        if isinstance(self.stage, Wait) and not getattr(result, self.stage.ready_field):
            await self.wait_again(connection, body, run_id, now)
            return
        if not await self.queue.finish(connection, self.ticket, body, run_id):
            raise StaleAttempt()
        await connection.execute(
            update(stages)
            .where(stages.c.id == self.row["id"])
            .values(
                state="succeeded",
                output_json=body,
                run_id=run_id,
                finished_at=now,
                elapsed_ms=stages.c.elapsed_ms + (now - self.row["started_at"]) * 1000,
            )
        )
        index = next(
            i for i, stage in enumerate(self.pipeline.stages) if stage.name == self.stage.name
        )
        if index + 1 < len(self.pipeline.stages):
            await self.queue.pipelines.enqueue(connection, root, self.pipeline, index + 1)
        else:
            await connection.execute(
                update(runs)
                .where(runs.c.id == root["id"])
                .values(
                    state="succeeded",
                    finished_at=now,
                    updated_at=now,
                    reason="",
                )
            )
            await self.queue.pipelines.next_cycle(connection, root)

    # 一次查询结束立即释放事务与租约，不在任务里sleep等待上游。
    async def wait_again(
        self, connection: AsyncConnection, body: str, run_id: str, now: float
    ) -> None:
        assert isinstance(self.stage, Wait)
        await connection.execute(
            update(jobs)
            .where(jobs.c.id == self.ticket.id)
            .values(
                state="waiting_retry",
                run_after=min(now + self.stage.every, self.row["wait_until"]),
                lease_until=None,
                updated_at=now,
                last_run_id=run_id,
                result_json=body,
            )
        )
        await connection.execute(
            update(stages)
            .where(stages.c.id == self.row["id"])
            .values(
                state="waiting_external",
                output_json=body,
                run_id=run_id,
                poll_count=stages.c.poll_count + 1,
                elapsed_ms=stages.c.elapsed_ms + (now - self.row["started_at"]) * 1000,
            )
        )
        await connection.execute(
            update(runs)
            .where(runs.c.id == self.root["id"])
            .values(
                state="waiting_external",
                updated_at=now,
            )
        )


# 阶段任务检查只读取真实关联记录，不能靠伪造任务key绕过版本限制。
async def prepare(queue: "JobQueue", ticket: "Ticket") -> StageContext | None:
    if not is_pipeline_job(ticket):
        return None
    async with queue.database.write() as connection:
        row = await stage_for(connection, ticket.id)
        if row is None:
            return None
        await own(connection, ticket)
        root = await root_for(connection, row["pipeline_id"])
        pipeline = queue.catalog.pipelines.get(root["pipeline"])
        stage = (
            next((s for s in pipeline.stages if s.name == row["name"]), None) if pipeline else None
        )
        context = StageContext(queue, ticket, root, row, pipeline, stage)
        state, code, reason = await decision(connection, context)
    if reason:
        context.allowed = False
        await queue.fail(ticket, state, code, reason, run_after=time.time() + 1)
    return context


# 当前阶段和未来阶段格式一致才执行，模块版本变化本身不影响继续运行。
async def decision(connection: AsyncConnection, context: StageContext) -> tuple[str, str, str]:
    queue, ticket, root, row = context.queue, context.ticket, context.root, context.row
    pipeline, stage = context.pipeline, context.stage
    if root["current_stage"] != row["name"] or root["state"] not in ("running", "waiting_external"):
        return "blocked", "pipeline_inactive", "流程当前不允许执行此阶段"
    if (
        pipeline is None
        or stage is None
        or not compatible(root, declarations(pipeline, queue.catalog))
    ):
        return (
            "blocked",
            "pipeline_schema_changed",
            f"流程阶段{row['name']}或后续阶段格式/声明已变化",
        )
    now = time.time()
    wait_until = row["wait_until"]
    if isinstance(stage, Wait):
        wait_until = wait_until or now + stage.timeout
        if now >= wait_until:
            return "failed", "pipeline_wait_timeout", f"流程阶段{stage.name}等待已超时"
        if not await wait_capacity(connection, context):
            return "waiting_retry", "pipeline_capacity", f"流程阶段{stage.name}等待检查容量"
    await own(connection, ticket)
    version = queue.catalog.binding(stage.operation).module.version
    row.update(started_at=now, wait_until=wait_until, module_version=version)
    await connection.execute(
        update(stages)
        .where(stages.c.id == row["id"])
        .values(
            state="running",
            started_at=now,
            wait_until=wait_until,
            module_version=version,
            attempt=ticket.attempt,
            error="",
        )
    )
    await connection.execute(
        update(runs).where(runs.c.id == root["id"]).values(state="running", updated_at=now)
    )
    return "", "", ""


# 同一个等待阶段跨流程运行也受max_parallel限制，过期租约不占执行名额。
async def wait_capacity(connection: AsyncConnection, context: StageContext) -> bool:
    assert isinstance(context.stage, Wait)
    await connection.execute(
        select(job_counts.c.contract)
        .where(job_counts.c.contract == context.ticket.contract)
        .with_for_update()
    )
    count = await connection.scalar(
        select(func.count())
        .select_from(
            stages.join(runs, stages.c.pipeline_id == runs.c.id).join(
                jobs, stages.c.job_id == jobs.c.id
            )
        )
        .where(
            runs.c.pipeline == context.root["pipeline"],
            stages.c.name == context.stage.name,
            stages.c.state == "running",
            jobs.c.state == "running",
            jobs.c.lease_until > time.time(),
            jobs.c.id != context.ticket.id,
        )
    )
    return int(count or 0) < context.stage.max_parallel
