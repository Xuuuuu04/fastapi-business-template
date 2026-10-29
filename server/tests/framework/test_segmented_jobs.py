import asyncio
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import func, insert, select, update

from app.setup.build import Services, build
from shared.access.caller import SYSTEM
from shared.errors.framework import DeclarationError, StepRuleBroken
from shared.jobs.checkpoint import Checkpoint
from shared.jobs.tables import checkpoints, jobs, segments
from shared.jobs.views import get_job, requeue
from shared.jobs.worker import Worker, WorkerOptions
from shared.modules.catalog import Catalog
from shared.records.stores import RunFilter
from tests.framework.sample_modules import SampleBusy
from tests.framework.segment_sample import (
    BatchInput,
    BatchStore,
    batch,
    module,
    output,
    sample_metadata,
    source,
)
from tests.testing_app import make_settings, prepare_test_database

pytestmark = pytest.mark.anyio


@pytest.fixture
async def segmented(tmp_path: Path):
    settings = make_settings(tmp_path)
    await prepare_test_database(settings.database_url)
    built = build(settings, modules=[module])
    async with built.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
    try:
        yield built
    finally:
        async with built.database.write() as connection:
            await connection.run_sync(sample_metadata.drop_all)
        await built.close()


async def submit(services: Services, total: int = 100000, **options) -> str:
    async with services.database.write() as connection:
        await connection.execute(insert(source), [{"id": i} for i in range(1, total + 1)])
    return await services.runtime.submit(batch, BatchInput(total=total, **options), caller=SYSTEM)


async def execute(services: Services, ticket=None) -> None:
    ticket = ticket or await services.queue.claim(time.time())
    assert ticket is not None
    await Worker(services.runtime, services.queue, [], WorkerOptions()).execute(ticket)


async def assert_complete(services: Services, job_id: str, total: int) -> None:
    async with services.database.read() as connection:
        result = (
            await connection.execute(
                select(
                    func.count(),
                    func.min(output.c.id),
                    func.max(output.c.id),
                    func.sum(output.c.value),
                )
            )
        ).one()
        evidence = (
            (
                await connection.execute(
                    select(segments).where(segments.c.job_id == job_id).order_by(segments.c.number)
                )
            )
            .mappings()
            .all()
        )
    assert tuple(result) == (total, 1, total, total * (total + 1))
    assert sum(row["rows"] for row in evidence) == total
    assert [row["number"] for row in evidence] == list(range(1, len(evidence) + 1))
    assert all(row["run_id"] and row["elapsed_ms"] > 0 for row in evidence)
    job = await get_job(services.database, job_id)
    assert job is not None and job.state == "done" and job.result == {"processed": total}


async def test_100000_rows_resume_after_sigkill(segmented: Services, tmp_path: Path) -> None:
    signal = tmp_path / "batch-paused"
    job_id = await submit(segmented, pause_after=10000, signal_file=str(signal))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.framework.segment_worker",
        str(tmp_path),
        segmented.settings.database_url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(30):
            while not signal.exists() and process.returncode is None:
                await asyncio.sleep(0.02)
        assert signal.exists()
        process.kill()
        await process.communicate()
        assert process.returncode == -9
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
    async with segmented.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 10000
        assert await connection.scalar(select(checkpoints.c.number)) == 2
    async with segmented.database.write() as connection:
        await connection.execute(update(jobs).values(lease_until=time.time() - 1))
    assert await segmented.queue.reclaim(time.time()) == 1
    await execute(segmented)
    await assert_complete(segmented, job_id, 100000)
    async with segmented.database.read() as connection:
        evidence = (
            (await connection.execute(select(segments).order_by(segments.c.number)))
            .mappings()
            .all()
        )
    assert [row["attempt"] for row in evidence[:2]] == [1, 1]
    assert all(row["attempt"] == 2 for row in evidence[2:])
    records = await segmented.runtime.recorder.recent(RunFilter(job_id=job_id), 30)
    assert any(run.segment_committed and "5000行" in run.summary for run in records)


async def test_failed_batch_keeps_previous_checkpoint(segmented: Services, monkeypatch) -> None:
    job_id = await submit(segmented, total=15000)
    original = BatchStore.save

    async def fail_second(self, start, end):
        count = await original(self, start, end)
        if start == 5000:
            raise SampleBusy()
        return count

    monkeypatch.setattr(BatchStore, "save", fail_second)
    await execute(segmented)
    async with segmented.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 5000
        assert await connection.scalar(select(checkpoints.c.number)) == 1
    monkeypatch.setattr(BatchStore, "save", original)
    await execute(segmented)
    await assert_complete(segmented, job_id, 15000)


async def test_expired_attempt_cannot_commit(segmented: Services) -> None:
    job_id = await submit(segmented, total=5000)
    old = await segmented.queue.claim(time.time())
    async with segmented.database.write() as connection:
        await connection.execute(update(jobs).values(lease_until=time.time() - 1))
    await execute(segmented, old)
    async with segmented.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 0
        assert await connection.scalar(select(checkpoints.c.number)) == 0
    await segmented.queue.reclaim(time.time())
    new = await segmented.queue.claim(time.time())
    assert new is not None and new.attempt == 2
    await execute(segmented, old)
    await execute(segmented, new)
    await assert_complete(segmented, job_id, 5000)


async def test_checkpoint_requires_segmented_worker(segmented: Services) -> None:
    with pytest.raises(StepRuleBroken, match="后台任务"):
        await segmented.runtime.run(batch, BatchInput(), caller=SYSTEM)


def test_segmented_declaration_requires_safe_batches() -> None:
    unsafe = replace(module, jobs=(replace(module.jobs[0], repeat_safe=False),))
    with pytest.raises(DeclarationError, match="repeat_safe"):
        Catalog([unsafe])


async def test_checkpoint_cursor_rules() -> None:
    async def before_write():
        pass

    checkpoint = Checkpoint(0, {}, before_write)
    for cursor in ({}, {"bad": object()}, {"bad": float("nan")}, {"big": "x" * 17000}):
        with pytest.raises(StepRuleBroken):
            checkpoint.advance(cursor, rows=1)
    checkpoint.advance({"after": 1}, rows=1)
    with pytest.raises(StepRuleBroken):
        checkpoint.finish()


async def test_manual_recovery_starts_at_failed_batch(segmented: Services, monkeypatch) -> None:
    job_id = await submit(segmented, total=15000)
    original = BatchStore.save

    async def fail_second(self, start, end):
        count = await original(self, start, end)
        if start == 5000:
            raise ValueError("合成程序错误")
        return count

    monkeypatch.setattr(BatchStore, "save", fail_second)
    await execute(segmented)
    job = await get_job(segmented.database, job_id)
    assert job is not None and job.state == "failed"
    monkeypatch.setattr(BatchStore, "save", original)
    assert (
        await requeue(segmented.database, segmented.catalog, job_id, accept_version=False)
        == "已重新排队"
    )
    await execute(segmented)
    await assert_complete(segmented, job_id, 15000)


async def test_missing_checkpoint_rolls_back_batch(segmented: Services, monkeypatch) -> None:
    def forget(self, **kwargs):
        pass

    monkeypatch.setattr(Checkpoint, "finish", forget)
    await submit(segmented, total=5000)
    await execute(segmented)
    async with segmented.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 0
        assert await connection.scalar(select(checkpoints.c.number)) == 0
