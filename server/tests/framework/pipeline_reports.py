import json

import pytest
from sqlalchemy import select

from shared.db.database import Database
from shared.jobs.tables import job_counts, jobs
from shared.pipelines.tables import members, runs, stages
from tests.failure_reports import FAILURE_FILE

COLUMNS = {
    runs: ("id", "pipeline", "org_id", "state", "current_stage", "reason", "updated_at"),
    stages: ("id", "pipeline_id", "name", "state", "job_id", "run_id", "error"),
    members: (
        "id",
        "pipeline_id",
        "stage_id",
        "key",
        "state",
        "phase_name",
        "job_id",
        "run_id",
        "attempt",
        "accepted",
        "wait_until",
        "started_at",
        "updated_at",
        "error",
    ),
    jobs: (
        "id",
        "contract",
        "state",
        "attempt",
        "run_after",
        "lease_until",
        "last_run_id",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
        "finished_at",
    ),
    job_counts: ("contract", "active"),
}


async def save_failed_pipeline(item: pytest.Item, database: Database) -> None:
    path = item.stash.get(FAILURE_FILE, None)
    if path is None:
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    snapshot = {}
    async with database.read() as connection:
        for table, names in COLUMNS.items():
            rows = await connection.execute(select(*(table.c[name] for name in names)))
            snapshot[table.name] = [dict(row) for row in rows.mappings()]
    data["pipeline_snapshot"] = snapshot
    data["database"] = "sqlite" if database.is_sqlite else "postgresql"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
