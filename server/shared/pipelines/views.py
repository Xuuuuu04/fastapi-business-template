import json
from typing import Any

from sqlalchemy import select

from shared.db.database import Database
from shared.graphs.mermaid import label
from shared.jobs.checkpoint_store import progress_map
from shared.pipelines.member_views import group_summaries
from shared.pipelines.tables import notifications, runs, stages


async def list_runs(
    database: Database, *, org_id: str = "*", limit: int = 50
) -> list[dict[str, Any]]:
    query = select(runs).order_by(runs.c.created_at.desc()).limit(limit)
    if org_id != "*":
        query = query.where(runs.c.org_id == org_id)
    async with database.read() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [summary(dict(row)) for row in rows]


async def detail(database: Database, run_id: str, *, org_id: str = "*") -> dict[str, Any] | None:
    query = select(runs).where(runs.c.id == run_id)
    if org_id != "*":
        query = query.where(runs.c.org_id == org_id)
    async with database.read() as connection:
        row = (await connection.execute(query)).mappings().first()
        if row is None:
            return None
        rows = (
            (
                await connection.execute(
                    select(stages).where(stages.c.pipeline_id == run_id).order_by(stages.c.position)
                )
            )
            .mappings()
            .all()
        )
    checkpoints = await progress_map(database, [stage["job_id"] for stage in rows])
    items = [stage_item(stage, checkpoints) for stage in rows]
    groups = await group_summaries(database, run_id)
    for item in items:
        if item["name"] in groups:
            item["members"] = groups[item["name"]]
    items = complete_stages(json.loads(row["declarations_json"]), items)
    result = summary(dict(row))
    result["stages"] = items
    result["graph"] = graph(items)
    result["notification_state"] = await notification_state(database, run_id)
    result["source_fixed"] = row["source_json"] is not None
    return result


def stage_item(stage: Any, checkpoints: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item = {
        key: stage[key]
        for key in (
            "name",
            "contract",
            "state",
            "job_id",
            "run_id",
            "module_version",
            "attempt",
            "poll_count",
            "elapsed_ms",
            "error",
        )
    }
    if stage["started_at"] is None:
        item["elapsed_ms"] = None
    item["checkpoint"] = checkpoints.get(stage["job_id"])
    item["run_url"] = f"/api/system/runs/{stage['run_id']}" if stage["run_id"] else None
    return item


def summary(row: dict) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "id",
            "pipeline",
            "org_id",
            "cycle_key",
            "state",
            "current_stage",
            "created_at",
            "updated_at",
            "finished_at",
            "reason",
            "complete_by",
            "overdue",
            "overdue_at",
            "on_overdue",
        )
    }


def graph(items: list[dict[str, Any]]) -> str:
    lines = ["flowchart LR"]
    for index, item in enumerate(items):
        elapsed = "耗时未知" if item["elapsed_ms"] is None else f"{item['elapsed_ms']:.1f}ms"
        text = label(f"{item['name']} {item['state']} {elapsed}")
        lines.append(f'  s{index}["{text}"]')
        if index:
            lines.append(f"  s{index - 1} --> s{index}")
    return "\n".join(lines)


def complete_stages(
    declared: list[dict[str, str]], items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    actual = {item["name"]: item for item in items}
    result = []
    for stage in declared:
        result.append(
            actual.pop(stage["name"], {})
            or dict(
                name=stage["name"],
                contract=stage.get("contract", "未知"),
                state="not_started",
                job_id="",
                run_id="",
                run_url=None,
                module_version="",
                attempt=0,
                poll_count=0,
                elapsed_ms=None,
                error="",
                checkpoint=None,
            )
        )
    return result + list(actual.values())


async def notification_state(database: Database, run_id: str) -> str | None:
    async with database.read() as connection:
        return await connection.scalar(
            select(notifications.c.state).where(
                notifications.c.kind == "pipeline_overdue", notifications.c.key == run_id
            )
        )
