"""
流程的启动与阶段派发：周期唯一，重叠周期明确skip或queue，下一阶段与产出同事务登记。
"""

import json
import secrets
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller, caller_from_record
from shared.data.models import Data
from shared.errors.framework import DuplicateRequest, InvalidInput, NotAllowed, StepRuleBroken
from shared.modules.contract import Contract
from shared.pipelines.overdue import deadline
from shared.pipelines.plan import Pipeline, PipelineView, StartInput, StartRequest, Wait
from shared.pipelines.schema import data_json, declarations, input_source
from shared.pipelines.storage import ACTIVE, PREFIX, compatible
from shared.pipelines.tables import runs, stages

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue


# 使用同一个任务队列，不在流程内部另造执行器。
class PipelineEngine:
    # 保存目录与数据库入口，不在构造时访问数据库。
    def __init__(self, queue: "JobQueue") -> None:
        self.queue = queue
        self.catalog, self.database = queue.catalog, queue.database

    # 每轮worker短事务检查成员空位，队列容量恢复后自动继续。
    async def reconcile(self) -> None:
        import time

        from shared.pipelines.member_reconcile import reconcile
        from shared.pipelines.overdue import check

        await check(self.queue, time.time())
        await reconcile(self.queue)

    # 定时任务的启动入口直接派发第一阶段，不额外占用启动任务。
    async def submit(
        self, connection: AsyncConnection, item: Contract[Any, Any], input: Data, caller: Caller
    ) -> str:
        if not isinstance(input, StartInput):
            raise StepRuleBroken("流程启动输入必须是StartInput")
        result = await self.start(
            connection, self.catalog.pipeline_starts[item.name], input.request, caller
        )
        return result.id

    # 周期重复触发返回原流程；不同输入不能借用同一个周期。
    async def start(
        self, connection: AsyncConnection, pipeline: Pipeline, request: StartRequest, caller: Caller
    ) -> PipelineView:
        key = request.cycle_key or (request.period.isoformat() if request.period else "")
        if not key or len(key) > 120:
            raise InvalidInput(f"流程{pipeline.name}需要不超过120字符的周期键或period")
        if not caller.org_id:
            raise NotAllowed("启动流程需要明确组织身份")
        body = data_json(pipeline.input, request.data, "input")
        row = self.new_root(pipeline, caller, key, body)
        row["complete_by"] = deadline(pipeline, request, row["created_at"])
        row["on_overdue"] = pipeline.on_overdue
        row["overdue"] = False
        existing = await self.insert_root(connection, row)
        if existing:
            return existing
        active = await self.active(connection, pipeline.name, caller.org_id)
        if active is not None:
            state = "skipped" if pipeline.overlap == "skip" else "queued"
            await connection.execute(
                update(runs)
                .where(runs.c.id == row["id"])
                .values(
                    state=state,
                    reason=f"上一周期{active}尚未结束",
                    finished_at=time.time() if state == "skipped" else None,
                )
            )
            return PipelineView(id=row["id"], state=state)
        try:
            async with connection.begin_nested():
                await self.claim_cycle(connection, dict(row), pipeline)
        except IntegrityError:
            state = "skipped" if pipeline.overlap == "skip" else "queued"
            await connection.execute(
                update(runs)
                .where(runs.c.id == row["id"])
                .values(
                    state=state,
                    reason="另一周期同时取得执行名额",
                    finished_at=time.time() if state == "skipped" else None,
                )
            )
            return PipelineView(id=row["id"], state=state)
        await self.enqueue(connection, dict(row), pipeline, 0)
        return PipelineView(id=row["id"], state="running")

    # 起始数据与调用身份在登记时冻结。
    def new_root(self, pipeline: Pipeline, caller: Caller, key: str, body: str) -> dict:
        return dict(
            id=secrets.token_hex(8),
            pipeline=pipeline.name,
            org_id=caller.org_id,
            cycle_key=key,
            state="queued",
            current_stage="",
            input_json=body,
            declarations_json=json.dumps(declarations(pipeline, self.catalog)),
            caller_json=json.dumps(caller.to_record()),
            created_at=time.time(),
            updated_at=time.time(),
            reason="",
        )

    # 唯一周期以数据库约束为准，重复请求只复用原记录。
    async def insert_root(self, connection: AsyncConnection, row: dict) -> PipelineView | None:
        try:
            async with connection.begin_nested():
                await connection.execute(insert(runs).values(**row))
        except IntegrityError:
            saved = (
                (
                    await connection.execute(
                        select(runs).where(
                            runs.c.pipeline == row["pipeline"],
                            runs.c.org_id == row["org_id"],
                            runs.c.cycle_key == row["cycle_key"],
                        )
                    )
                )
                .mappings()
                .one()
            )
            if saved["input_json"] != row["input_json"]:
                raise DuplicateRequest("同一流程周期已经使用了不同输入") from None
            return PipelineView(id=saved["id"], state=saved["state"], reused=True)
        return None

    # 查询同组织同流程的活动周期，完成或失败后的周期不占名额。
    async def active(self, connection: AsyncConnection, name: str, org: str) -> str | None:
        return await connection.scalar(
            select(runs.c.id)
            .where(
                runs.c.pipeline == name,
                runs.c.org_id == org,
                runs.c.state.in_(ACTIVE),
            )
            .with_for_update()
        )

    # 取得唯一执行名额并登记第一阶段；初始输入只在启动时校验一次。
    async def claim_cycle(
        self, connection: AsyncConnection, root: dict, pipeline: Pipeline
    ) -> None:
        await connection.execute(
            update(runs)
            .where(runs.c.id == root["id"])
            .values(
                state="running",
                current_stage=pipeline.stages[0].name,
                reason="",
                updated_at=time.time(),
            )
        )

    # 排队周期取得名额后登记首阶段，提交仍在同一个事务。
    async def activate(self, connection: AsyncConnection, root: dict, pipeline: Pipeline) -> None:
        await self.claim_cycle(connection, root, pipeline)
        await self.enqueue(connection, root, pipeline, 0)
        if root.get("overdue") and root.get("on_overdue") == "pause":
            await connection.execute(
                update(runs).where(runs.c.id == root["id"]).values(state="overdue_paused")
            )

    # 阶段输入来自初始Data或某个已成功阶段的有界产出。
    async def enqueue(
        self, connection: AsyncConnection, root: dict, pipeline: Pipeline, index: int
    ) -> None:
        stage = pipeline.stages[index]
        input, body = await self.stage_input(connection, root, pipeline, index)
        stage_id = secrets.token_hex(8)
        caller = caller_from_record(json.loads(root["caller_json"]))
        job_id = await self.queue.submit(
            connection, stage.operation, input, caller, key=PREFIX + stage_id, request_id=""
        )
        await connection.execute(
            insert(stages).values(
                id=stage_id,
                pipeline_id=root["id"],
                name=stage.name,
                position=index,
                contract=stage.operation.name,
                job_id=job_id,
                state="queued",
                input_json=body,
                run_id="",
                module_version="",
                attempt=0,
                poll_count=0,
                created_at=time.time(),
                elapsed_ms=0,
                wait_until=time.time() + stage.timeout if isinstance(stage, Wait) else None,
                error="",
            )
        )
        await connection.execute(
            update(runs)
            .where(runs.c.id == root["id"])
            .values(
                current_stage=stage.name,
                state="overdue_paused" if root["state"] == "overdue_paused" else "running",
                updated_at=time.time(),
                reason="",
            )
        )

    # 来源必须已成功，输入再次按当前阶段Data校验并限制大小。
    async def stage_input(
        self, connection: AsyncConnection, root: dict, pipeline: Pipeline, index: int
    ) -> tuple[Data, str]:
        stage, source = pipeline.stages[index], input_source(pipeline, index)
        body = (
            root["input_json"]
            if source == "input"
            else await connection.scalar(
                select(stages.c.output_json).where(
                    stages.c.pipeline_id == root["id"],
                    stages.c.name == source,
                    stages.c.state == "succeeded",
                )
            )
        )
        if body is None:
            raise InvalidInput(f"流程阶段{stage.name}缺少已成功来源{source}")
        input = stage.operation.input.model_validate_json(body)
        body = data_json(stage.operation.input, input, stage.name)
        return input, body

    # 结束一个周期后同事务唤醒最早排队周期，不依赖内存计时器。
    async def next_cycle(self, connection: AsyncConnection, root: dict) -> None:
        pipeline = self.catalog.pipelines.get(root["pipeline"])
        if pipeline is None:
            return
        row = (
            (
                await connection.execute(
                    select(runs)
                    .where(
                        runs.c.pipeline == root["pipeline"],
                        runs.c.org_id == root["org_id"],
                        runs.c.state == "queued",
                    )
                    .order_by(runs.c.created_at, runs.c.id)
                    .limit(1)
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if row:
            pending = dict(row)
            pending["current_stage"] = pipeline.stages[0].name
            if not compatible(pending, declarations(pipeline, self.catalog)):
                await connection.execute(
                    update(runs)
                    .where(runs.c.id == row["id"])
                    .values(
                        state="version_blocked",
                        current_stage=pending["current_stage"],
                        reason="排队期间阶段格式或声明变化，等待人工确认",
                        updated_at=time.time(),
                    )
                )
                return
            await self.activate(connection, pending, pipeline)
