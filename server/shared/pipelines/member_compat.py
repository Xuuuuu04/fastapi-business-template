import json
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.pipelines.plan import FanOut, Pipeline
from shared.pipelines.schema import declarations, group_signature, stage_declaration
from shared.pipelines.storage import compatible
from shared.pipelines.tables import runs, stages

if TYPE_CHECKING:
    from shared.modules.catalog import Catalog


def group_compatible(root: dict, group: FanOut, pipeline: Pipeline, catalog: "Catalog") -> bool:
    saved = json.loads(root["declarations_json"])
    item = next((item for item in saved if item["name"] == group.name), None)
    if item is None or item.get("group") != group_signature(group):
        return False
    index = next(i for i, stage in enumerate(pipeline.stages) if stage.name == group.name)
    if index + 1 == len(pipeline.stages):
        return True
    future = dict(root, current_stage=pipeline.stages[index + 1].name)
    return compatible(future, declarations(pipeline, catalog))


def member_compatible(member: dict, group: FanOut, catalog: "Catalog") -> bool:
    snapshot = dict(
        declarations_json=member["declarations_json"], current_stage=member["phase_name"]
    )
    return compatible(snapshot, [stage_declaration(stage, catalog) for stage in group.stages])


async def block(connection: AsyncConnection, root: dict, stage: dict, reason: str) -> None:
    await connection.execute(
        update(runs).where(runs.c.id == root["id"]).values(state="version_blocked", reason=reason)
    )
    await connection.execute(
        update(stages)
        .where(stages.c.id == stage["id"])
        .values(state="version_blocked", error=reason)
    )
    root["state"] = "version_blocked"
