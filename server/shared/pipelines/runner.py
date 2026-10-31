import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.errors.framework import InvalidInput, StaleAttempt
from shared.jobs.tables import job_counts, jobs
from shared.pipelines.context import ExecutionContext
from shared.pipelines.member_pool import planned
from shared.pipelines.plan import FanOut, Pipeline, Stage, Wait
from shared.pipelines.schema import data_json, declarations, format_of
from shared.pipelines.storage import compatible, is_pipeline_job, own, root_for, stage_for
from shared.pipelines.tables import runs, stages
from shared.scenarios.observations import ObservationPosition
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue, Ticket


@dataclass
class StageContext:
    queue: "JobQueue"
    ticket: "Ticket"
    root: dict
    row: dict
    pipeline: Pipeline | None
    stage: Stage | None
    allowed: bool = True

    @property
    def observation_position(self) -> ObservationPosition:
        return ObservationPosition(attempt=self.ticket.attempt)

    async def finish(self, connection: AsyncConnection, result: Data, run_id: str) -> None:
        assert self.stage is not None and self.pipeline is not None
        body = data_json(self.stage.operation.output, result, self.stage.name)
        await own(connection, self.ticket)
        root = await root_for(connection, self.root["id"])
        if root["current_stage"] != self.stage.name or root["state"] not in (
            "running",
            "waiting_external",
            "overdue_paused",
        ):
            raise StaleAttempt()
        if self.stage.freeze_sources:
            await connection.execute(
                update(runs)
                .where(runs.c.id == root["id"])
                .values(
                    source_json=body,
                    source_schema_json=json.dumps(format_of(self.stage.operation.output)),
                )
            )
        now = business_now()
        if isinstance(self.stage, Wait) and now >= self.row["wait_until"]:
            raise InvalidInput(f"流程阶段 {self.stage.name} 等待超时")
        if isinstance(self.stage, Wait) and not getattr(result, self.stage.ready_field):
            await self.wait_again(connection, body, run_id, now)
            return
        if not await self.queue.finish(connection, self.ticket, body, run_id):
            raise StaleAttempt()
        if isinstance(self.stage, FanOut):
            await planned(connection, self.queue, root, self.row, self.stage, body, run_id)
            return
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
        await self.advance(connection, root, now)
        if root["state"] == "overdue_paused" and self.stage.name != self.pipeline.stages[-1].name:
            await connection.execute(
                update(runs).where(runs.c.id == root["id"]).values(state="overdue_paused")
            )

    async def advance(self, connection: AsyncConnection, root: dict, now: float) -> None:
        assert self.pipeline is not None and self.stage is not None
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


async def prepare(queue: "JobQueue", ticket: "Ticket") -> ExecutionContext | None:
    if not is_pipeline_job(ticket):
        return None
    async with queue.database.read() as connection:
        row = await stage_for(connection, ticket.id)
    if row is None:
        from shared.pipelines.member_runner import prepare as prepare_member

        return await prepare_member(queue, ticket)
    async with queue.database.write() as connection:
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
        await queue.fail(ticket, state, code, reason, run_after=business_now() + 1)
    return context


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
            f"流程阶段 {row['name']} 或后续阶段的数据格式或执行配置已改变",
        )
    now = business_now()
    wait_until = row["wait_until"]
    if isinstance(stage, Wait):
        wait_until = wait_until or now + stage.timeout
        if now >= wait_until:
            return "failed", "pipeline_wait_timeout", f"流程阶段 {stage.name} 等待超时"
        if not await wait_capacity(connection, context):
            return (
                "waiting_retry",
                "pipeline_capacity",
                f"流程阶段 {stage.name} 正在等待可用的检查任务名额",
            )
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
            jobs.c.lease_until > business_now(),
            jobs.c.id != context.ticket.id,
        )
    )
    return int(count or 0) < context.stage.max_parallel
