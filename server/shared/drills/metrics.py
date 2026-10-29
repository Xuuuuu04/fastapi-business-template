import asyncio
import json
import time
from contextlib import suppress
from typing import Any

import psutil
from sqlalchemy import select

from shared.db.database import Database
from shared.jobs.tables import jobs, segments
from shared.pipelines.tables import stages
from shared.records.recorder import Recorder
from shared.records.stores import RunFilter


class MemoryPeak:
    def __init__(self) -> None:
        self.peak = 0
        self.stop = asyncio.Event()

    async def sample(self) -> None:
        process = psutil.Process()
        while not self.stop.is_set():
            self.peak = max(self.peak, process.memory_info().rss)
            with suppress(TimeoutError):
                await asyncio.wait_for(self.stop.wait(), timeout=0.02)
        self.peak = max(self.peak, process.memory_info().rss)


async def report(database: Database, recorder: Recorder, run_id: str) -> list[dict[str, Any]]:
    async with database.read() as connection:
        rows = (
            (
                await connection.execute(
                    select(stages).where(stages.c.pipeline_id == run_id).order_by(stages.c.position)
                )
            )
            .mappings()
            .all()
        )
    result = []
    for row in rows:
        runs = await recorder.recent(RunFilter(job_id=row["job_id"], top_only=False), 10000)
        async with database.read() as connection:
            batches = (
                (
                    await connection.execute(
                        select(segments).where(segments.c.job_id == row["job_id"])
                    )
                )
                .mappings()
                .all()
            )
            body = await connection.scalar(
                select(jobs.c.result_json).where(jobs.c.id == row["job_id"])
            )
        payload = json.loads(body) if body else {}
        confirmed = confirmed_rows(batches, payload)
        elapsed = ((row["finished_at"] or time.time()) - row["created_at"]) * 1000
        result.append(
            dict(
                name=row["name"],
                state=row["state"],
                elapsed_ms=elapsed,
                recorded_compute_ms=sum(run.elapsed_ms for run in runs),
                rows=confirmed,
                row_evidence="已提交段"
                if batches
                else "操作输出"
                if confirmed is not None
                else "未知",
                run_ids=[run.id for run in runs],
                slow_sql=slow_sql(runs),
                query_budgets=query_budgets(runs),
            )
        )
    return result


def confirmed_rows(batches: Any, payload: dict[str, Any]) -> int | None:
    if batches:
        return sum(item["rows"] for item in batches)
    return payload.get("rows", payload.get("processed"))


def slow_sql(runs: list[Any]) -> list[dict[str, Any]]:
    calls = [
        dict(
            method=call.method,
            shape=call.statement,
            tables=call.tables,
            source=call.source,
            function=call.function,
            storage_source=call.storage_source,
            storage_function=call.storage_function,
            explain=call.explain,
            elapsed_ms=call.elapsed_ms,
            rows=call.rows,
        )
        for run in runs
        for step in run.steps
        for call in step.database
    ]
    return sorted(calls, key=lambda call: call["elapsed_ms"], reverse=True)[:5]


def query_budgets(runs: list[Any]) -> list[dict[str, Any]]:
    return [dict(run_id=run.id, operation=run.contract, **run.query_budget) for run in runs]
