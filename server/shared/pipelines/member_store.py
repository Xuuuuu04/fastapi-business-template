"""
稳定成员的登记及查询；成员数据有界，重试复用相同键和输入，不能换来源。
"""

import json
import secrets
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import DuplicateRequest, InvalidInput
from shared.pipelines.plan import FanOut, Member
from shared.pipelines.schema import data_json, stage_declaration
from shared.pipelines.tables import members
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.modules.catalog import Catalog


# 按任务实际关联查找成员，伪造专用key不会成为流程成员。
async def member_for(connection: AsyncConnection, job_id: str) -> dict[str, Any] | None:
    row = (
        (await connection.execute(select(members).where(members.c.job_id == job_id)))
        .mappings()
        .first()
    )
    return dict(row) if row else None


# 每次登记数量有界，业务规划可用PR1逐批提交；此时不占用后台排队名额。
async def add(
    connection: AsyncConnection,
    root: dict,
    stage: dict,
    group: FanOut,
    values: list[Member],
    catalog: "Catalog",
) -> int:
    if len(values) > 1000:
        raise InvalidInput(f"扇出阶段{group.name}每批最多登记1000个成员，请分批")
    model = group.stages[0].operation.input
    declared = json.dumps([stage_declaration(child, catalog) for child in group.stages])
    for value in values:
        body = data_json(model, value.input, group.name + "/" + value.key)
        now = business_now()
        row = dict(
            id=secrets.token_hex(8),
            pipeline_id=root["id"],
            stage_id=stage["id"],
            key=value.key,
            state="planned",
            position=0,
            phase_name=group.stages[0].name,
            job_id=None,
            input_json=body,
            current_input_json=body,
            output_json=None,
            history_json="[]",
            declarations_json=declared,
            run_id="",
            module_version="",
            attempt=0,
            elapsed_ms=0,
            error="",
            accepted=False,
            created_at=now,
            updated_at=now,
        )
        await insert_member(connection, row)
    return len(values)


# 数据库唯一约束保护并发重试；同键换输入明确拒绝。
async def insert_member(connection: AsyncConnection, row: dict) -> None:
    try:
        async with connection.begin_nested():
            await connection.execute(insert(members).values(**row))
    except IntegrityError:
        saved = await connection.scalar(
            select(members.c.input_json).where(
                members.c.stage_id == row["stage_id"], members.c.key == row["key"]
            )
        )
        if saved != row["input_json"]:
            raise DuplicateRequest(f"扇出成员{row['key']}已经登记不同输入") from None
