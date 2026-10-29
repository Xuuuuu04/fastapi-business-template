import asyncio
import time
from pathlib import Path
from typing import Any

from sqlalchemy import delete, exists, select

from shared.access.audit import audit_records
from shared.db.access import Db
from shared.jobs.tables import jobs
from shared.operations.config import OperationsConfig
from shared.pipelines.tables import members, runs, stages
from shared.records.tables import run_records

PHASES = ("members", "stages", "pipelines", "jobs", "runs", "audit", "uploads", "originals")


async def clean_db(db: Db, phase: str, cutoff: float, config: OperationsConfig) -> int:
    terminal = select(runs.c.id).where(
        runs.c.state.in_(("succeeded", "skipped")),
        runs.c.finished_at < cutoff - config.job_days * 86400,
    )
    choices: dict[str, tuple[Any, Any]] = {
        "members": (members, members.c.pipeline_id.in_(terminal)),
        "stages": (
            stages,
            stages.c.pipeline_id.in_(terminal)
            & ~exists(select(members.c.id).where(members.c.stage_id == stages.c.id)),
        ),
        "pipelines": (
            runs,
            runs.c.id.in_(terminal)
            & ~exists(select(stages.c.id).where(stages.c.pipeline_id == runs.c.id)),
        ),
        "jobs": (
            jobs,
            jobs.c.state.in_(("done", "cancelled"))
            & (jobs.c.finished_at < cutoff - config.job_days * 86400)
            & ~exists(select(stages.c.id).where(stages.c.job_id == jobs.c.id))
            & ~exists(select(members.c.id).where(members.c.job_id == jobs.c.id)),
        ),
        "runs": (
            run_records,
            (run_records.c.started_at < cutoff - config.run_days * 86400)
            & run_records.c.status.not_in(("running", "lost", "unknown"))
            & ~exists(
                select(jobs.c.id).where(
                    jobs.c.last_run_id == run_records.c.id, jobs.c.state.in_(("unknown", "blocked"))
                )
            ),
        ),
        "audit": (audit_records, audit_records.c.created_at < cutoff - config.audit_days * 86400),
    }
    table, condition = choices[phase]
    ids = select(table.c.id).where(condition).order_by(table.c.id).limit(config.batch_size)
    return await db.change(delete(table).where(table.c.id.in_(ids)))


def file_batch(root: Path, prefixes: list[str], older: float, limit: int) -> int:
    root = root.resolve()
    count = 0
    for prefix in prefixes:
        folder = root / prefix
        if not folder.resolve().is_relative_to(root) or folder.is_symlink() or not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            if path.stat().st_mtime >= older:
                continue
            path.unlink(missing_ok=True)
            count += 1
            if count == limit:
                return count
    return count


async def clean_files(settings: Any, phase: str, cutoff: float) -> int:
    config = settings.operations
    if phase == "originals" and settings.file_storage == "s3":
        return await asyncio.to_thread(clean_s3, settings, cutoff)
    root = Path(settings.upload_root if phase == "uploads" else settings.file_root)
    prefixes = ["."] if phase == "uploads" else config.original_prefixes
    days = config.upload_days if phase == "uploads" else config.original_days
    return await asyncio.to_thread(
        file_batch, root, prefixes, cutoff - days * 86400, config.batch_size
    )


def clean_s3(settings: Any, cutoff: float) -> int:
    from shared.files.storage import S3Files, S3Options

    client = S3Files(
        S3Options(
            settings.s3_bucket,
            settings.s3_endpoint,
            settings.s3_region,
            settings.s3_access_key,
            settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else "",
        )
    ).client
    count = 0
    for prefix in settings.operations.original_prefixes:
        pages = client.get_paginator("list_objects_v2").paginate(
            Bucket=settings.s3_bucket, Prefix=prefix.rstrip("/") + "/"
        )
        for page in pages:
            for item in page.get("Contents", []):
                if (
                    item["LastModified"].timestamp()
                    >= cutoff - settings.operations.original_days * 86400
                ):
                    continue
                client.delete_object(Bucket=settings.s3_bucket, Key=item["Key"])
                count += 1
                if count == settings.operations.batch_size:
                    return count
    return count


def initial_cursor(cursor: dict[str, Any]) -> tuple[int, float]:
    return int(cursor.get("phase", 0)), float(cursor.get("cutoff", time.time()))
