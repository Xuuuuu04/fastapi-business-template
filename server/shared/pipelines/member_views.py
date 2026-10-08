"""
扇出摘要和有界成员详情，不公开业务输入、来源内容或产出正文。
"""

import json
from typing import Any

from sqlalchemy import func, select

from shared.db.database import Database
from shared.pipelines.tables import members, stages


# 所有成员只取计数进入流程摘要，避免在大项目里展开200行正文。
async def group_summaries(database: Database, run_id: str) -> dict[str, dict[str, Any]]:
    query = (
        select(stages.c.name, members.c.state, func.count())
        .join(members, members.c.stage_id == stages.c.id)
        .where(stages.c.pipeline_id == run_id)
    )
    query = query.group_by(stages.c.name, members.c.state)
    async with database.read() as connection:
        rows = await connection.execute(query)
        accepted = await connection.execute(
            select(stages.c.name, func.count())
            .join(members, members.c.stage_id == stages.c.id)
            .where(stages.c.pipeline_id == run_id, members.c.accepted.is_(True))
            .group_by(stages.c.name)
        )
    result: dict[str, dict[str, Any]] = {}
    for name, state, count in rows:
        result.setdefault(name, {"states": {}, "accepted": 0})["states"][state] = int(count)
    for name, count in accepted:
        result[name]["accepted"] = int(count)
    return result


# 按稳定键查看成员，每个子阶段保留实际版本和运行记录链接。
async def listing(
    database: Database, run_id: str, stage: str, *, after: str = "", limit: int = 50
) -> dict[str, Any]:
    query = (
        select(members)
        .join(stages, members.c.stage_id == stages.c.id)
        .where(stages.c.pipeline_id == run_id, stages.c.name == stage, members.c.key > after)
    )
    async with database.read() as connection:
        rows = (
            (await connection.execute(query.order_by(members.c.key).limit(limit + 1)))
            .mappings()
            .all()
        )
    items = []
    for row in rows[:limit]:
        item = {
            key: row[key]
            for key in (
                "key",
                "state",
                "phase_name",
                "job_id",
                "run_id",
                "module_version",
                "attempt",
                "elapsed_ms",
                "error",
                "accepted",
            )
        }
        history = json.loads(row["history_json"])
        if not history and row["started_at"] is None:
            item["elapsed_ms"] = None
        item["history"] = [
            {key: part[key] for key in ("name", "job_id", "run_id", "module_version")}
            for part in history
        ]
        items.append(item)
    return {"items": items, "next_after": items[-1]["key"] if len(rows) > limit else ""}
