from pathlib import Path
from time import time as wall_time

import pytest
from sqlalchemy import func, insert, select

from app.setup.build import Services, build
from shared.jobs import queue as job_queue
from shared.jobs.tables import job_counts, jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.pipelines.plan import StartRequest
from shared.pipelines.tables import members, runs
from shared.public import ApplicationSpec
from shared.timing.clock import RealClock
from shared.timing.current import current_clock, use_clock
from tests.framework.fanout_sample import Begin, module, pipeline, sample_metadata, versions
from tests.framework.test_pipelines import CALLER
from tests.testing_app import make_settings, prepare_test_database


class PipelineClock(RealClock):
    simulated = True

    def __init__(self) -> None:
        self.value = wall_time()

    def now(self) -> float:
        return self.value

    def advance_to(self, value: float) -> None:
        self.value = max(self.value, value)


def now() -> float:
    return current_clock().now()


@pytest.fixture
async def fanout(tmp_path: Path, monkeypatch, request):
    clock = PipelineClock()
    settings = make_settings(tmp_path)
    await prepare_test_database(settings.database_url)
    built = build(settings, modules=[module], application=ApplicationSpec(clock=clock))
    async with built.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
        await connection.execute(insert(versions).values(version=1))
    try:
        with use_clock(clock):
            yield built
    finally:
        from tests.framework.pipeline_reports import save_failed_pipeline

        await save_failed_pipeline(request.node, built.database)
        async with built.database.write() as connection:
            await connection.run_sync(sample_metadata.drop_all)
        await built.close()


async def start(services: Services, count: int = 200) -> str:
    data = pipeline.start.input(
        request=StartRequest[Begin](data=Begin(count=count), cycle_key="members")
    )
    return await services.runtime.submit(pipeline.start, data, caller=CALLER)


async def drain(services: Services, run_id: str, *, limit: int = 2000) -> dict:
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    peak = 0
    for _ in range(limit):
        await services.queue.pipelines.reconcile()
        async with services.database.read() as connection:
            active = await connection.scalar(
                select(func.count())
                .select_from(members.join(jobs, members.c.job_id == jobs.c.id))
                .where(jobs.c.state.in_(("queued", "running", "waiting_retry")))
            )
            peak = max(peak, int(active or 0))
            counts = (await connection.execute(select(job_counts.c.active))).scalars().all()
            assert all(count <= 3 for count in counts)
            root = (
                (await connection.execute(select(runs).where(runs.c.id == run_id))).mappings().one()
            )
            if root["state"] in ("succeeded", "failed", "unknown", "version_blocked"):
                return dict(root, peak=peak)
            due = await connection.scalar(
                select(func.min(jobs.c.run_after)).where(jobs.c.state.in_(job_queue.READY))
            )
        if due is not None:
            services.queue.clock.advance_to(due)
        ticket = await services.queue.claim(now())
        if ticket is None:
            raise AssertionError("活动流程没有可推进成员或明确等待任务")
        await worker.execute(ticket)
    raise AssertionError("成员链没有在声明阶段数内结束")
