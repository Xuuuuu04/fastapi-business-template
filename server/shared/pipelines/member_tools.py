import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.pipelines.member_store import add, member_for
from shared.pipelines.plan import FanOut, Member, MemberPage, MemberResult, Pipeline, Stage
from shared.pipelines.schema import data_json, format_of
from shared.pipelines.storage import stage_for
from shared.pipelines.tables import members, runs, stages

if TYPE_CHECKING:
    from shared.pipelines.gate import PipelineGate


@asynccontextmanager
async def reader(gate: "PipelineGate") -> AsyncIterator[AsyncConnection]:
    if gate.scope.tx.connection is not None:
        yield gate.scope.tx.connection
    else:
        async with gate.scope.runtime.database.read() as connection:
            yield connection


async def locate(
    gate: "PipelineGate", connection: AsyncConnection
) -> tuple[dict, dict, Pipeline, Stage]:
    catalog = gate.scope.runtime.catalog
    row = await stage_for(connection, gate.scope.job_id)
    member = None if row else await member_for(connection, gate.scope.job_id)
    if member:
        found = (
            (await connection.execute(select(stages).where(stages.c.id == member["stage_id"])))
            .mappings()
            .one()
        )
        row = dict(found)
    if row is None:
        raise StepRuleBroken("pipeline工具只能在已登记流程的阶段任务内使用")
    found = (
        (await connection.execute(select(runs).where(runs.c.id == row["pipeline_id"])))
        .mappings()
        .one()
    )
    root = dict(found)
    pipeline = catalog.pipelines.get(root["pipeline"])
    if pipeline is None or root["org_id"] != gate.scope.caller.org_id:
        raise StepRuleBroken("流程或当前组织不匹配")
    stage = next(stage for stage in pipeline.stages if stage.name == row["name"])
    if member and isinstance(stage, FanOut):
        stage = next(child for child in stage.stages if child.name == member["phase_name"])
    return root, row, pipeline, stage


async def source[Source: Data](gate: "PipelineGate", model: type[Source]) -> Source:
    async with reader(gate) as connection:
        root, _, _, stage = await locate(gate, connection)
    if stage.source is not model or root["source_json"] is None:
        raise StepRuleBroken("阶段未声明该source Data，或首阶段尚未固定来源")
    if json.loads(root["source_schema_json"]) != format_of(model):
        raise StepRuleBroken("已固定来源格式与阶段声明不符，需要人工处理")
    return model.model_validate_json(root["source_json"])


async def add_members(gate: "PipelineGate", values: list[Member]) -> int:
    if not gate.saves:
        raise StepRuleBroken("登记成员需要saves=True")
    connection = await gate.scope.tx.writer(gate.scope.runtime.database, "登记扇出成员")
    root, row, _, stage = await locate(gate, connection)
    if not isinstance(stage, FanOut) or stage.operation.name != gate.run.contract:
        raise StepRuleBroken("只有FanOut规划操作能登记成员")
    if row["job_id"] != gate.scope.job_id or row["state"] != "running":
        raise StepRuleBroken("成员只能在规划阶段完成前登记")
    return await add(connection, root, row, stage, values, gate.scope.runtime.catalog)


async def results[Output: Data](
    gate: "PipelineGate", name: str, model: type[Output], after: str = "", limit: int = 50
) -> MemberPage[Output]:
    if not 1 <= limit <= 200:
        raise StepRuleBroken("成员结果每页需要1到200条")
    async with reader(gate) as connection:
        root, _, pipeline, current = await locate(gate, connection)
        if current.members.get(name) is not model:
            raise StepRuleBroken("成员结果需在当前阶段的members声明中明确Data类型")
        group = next((stage for stage in pipeline.stages if stage.name == name), None)
        if not isinstance(group, FanOut) or group.stages[-1].operation.output is not model:
            raise StepRuleBroken("成员结果必须引用已声明的FanOut及最终产出Data")
        query = (
            select(members)
            .join(stages, members.c.stage_id == stages.c.id)
            .where(
                members.c.pipeline_id == root["id"],
                stages.c.name == name,
                members.c.accepted.is_(True),
                members.c.key > after,
            )
            .order_by(members.c.key)
            .limit(limit + 1)
        )
        rows = (await connection.execute(query)).mappings().all()
    items = [
        cast(Any, MemberResult)[model](
            key=row["key"], result=model.model_validate_json(row["output_json"])
        )
        for row in rows[:limit]
    ]
    page = cast(Any, MemberPage)[model](
        items=items, next_after=items[-1].key if len(rows) > limit else ""
    )
    data_json(type(page), page, name + "结果页")
    return page
