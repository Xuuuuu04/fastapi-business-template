import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select

from app.setup.build import Services, build
from shared.access.caller import Caller
from shared.jobs.schedule import Scheduler
from shared.jobs.worker import Worker, WorkerOptions
from shared.pipelines.tables import runs, stages
from tests.framework.pipeline_sample import (
    Ref,
    StartRequest,
    Store,
    events,
    module,
    pipeline,
    sample_metadata,
)
from tests.testing_app import make_settings, prepare_test_database

pytestmark = pytest.mark.anyio
CALLER = Caller(
    kind="user", id="runner", name="流程验收", org_id="org-a", permissions=frozenset({"*"})
)


@pytest.fixture
async def piped(tmp_path: Path):
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


async def start(services: Services, cycle: str) -> str:
    data = pipeline.start.input(request=StartRequest[Ref](data=Ref(), cycle_key=cycle))
    return await services.runtime.submit(pipeline.start, data, caller=CALLER)


async def drain(services: Services) -> None:
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    for _ in range(30):
        ticket = await services.queue.claim(time.time() + 0.1)
        if ticket is None:
            return
        await worker.execute(ticket)
    raise AssertionError("流程没有在有限阶段内结束")


async def snapshot(services: Services, run_id: str):
    async with services.database.read() as connection:
        root = (await connection.execute(select(runs).where(runs.c.id == run_id))).mappings().one()
        rows = (
            (
                await connection.execute(
                    select(stages).where(stages.c.pipeline_id == run_id).order_by(stages.c.position)
                )
            )
            .mappings()
            .all()
        )
        marks = Counter((await connection.execute(select(events.c.mark))).scalars().all())
    return root, rows, marks


async def test_scheduled_four_stages_complete(piped: Services) -> None:
    scheduler = Scheduler(piped.catalog.schedules, piped.queue, piped.database)
    now = time.time()
    await scheduler.tick(now)
    await scheduler.tick(now)
    async with piped.database.read() as connection:
        run_id = (await connection.execute(select(runs.c.id))).scalar_one()
        assert len((await connection.execute(select(stages))).all()) == 1
    await drain(piped)
    root, rows, marks = await snapshot(piped, run_id)
    assert root["state"] == "succeeded"
    assert [row["state"] for row in rows] == ["succeeded"] * 4
    assert marks == {"choose": 1, "collect": 1, "wait": 2, "publish": 1}
    assert all(row["run_id"] and row["elapsed_ms"] > 0 for row in rows)
    assert rows[2]["poll_count"] == 1


async def test_duplicate_cycle_and_skip_overlap(piped: Services) -> None:
    first = await start(piped, "one")
    assert await start(piped, "one") == first
    second = await start(piped, "two")
    root, _, _ = await snapshot(piped, second)
    assert root["state"] == "skipped" and root["reason"]
    await drain(piped)


async def test_resume_failed_stage_only(piped: Services, monkeypatch) -> None:
    from shared.pipelines.recovery import resume

    original = Store.record

    async def fail(self, name, reference):
        result = await original(self, name, reference)
        if name == "collect":
            raise ValueError("采集合成故障")
        return result

    monkeypatch.setattr(Store, "record", fail)
    run_id = await start(piped, "failure")
    await drain(piped)
    root, rows, marks = await snapshot(piped, run_id)
    assert root["state"] == "failed" and marks == {"choose": 1}
    assert rows[1]["elapsed_ms"] > 0
    first_run = rows[0]["run_id"]
    monkeypatch.setattr(Store, "record", original)
    await resume(piped.database, piped.catalog, run_id)
    await drain(piped)
    root, rows, marks = await snapshot(piped, run_id)
    assert root["state"] == "succeeded" and rows[0]["run_id"] == first_run
    assert marks == {"choose": 1, "collect": 1, "wait": 2, "publish": 1}


async def test_version_compatibility(piped: Services) -> None:
    from shared.modules.catalog import Catalog
    from shared.pipelines.recovery import resume

    run_id = await start(piped, "version")
    ticket = await piped.queue.claim(time.time())
    assert ticket is not None
    newer = replace(module, version="2")
    piped.queue.catalog = piped.runtime.catalog = Catalog([newer])
    piped.queue.pipelines.catalog = piped.queue.catalog
    await Worker(piped.runtime, piped.queue, [], WorkerOptions()).execute(ticket)
    root, rows, _ = await snapshot(piped, run_id)
    assert root["state"] == "running" and rows[0]["module_version"] == "2"
    changed = replace(
        pipeline,
        stages=tuple(
            replace(stage, every=0.002) if stage.name == "wait" else stage
            for stage in pipeline.stages
        ),
    )
    piped.catalog = piped.queue.catalog = piped.runtime.catalog = Catalog(
        [
            replace(
                newer,
                pipelines=(changed,),
                schedules=(replace(module.schedules[0], contract=changed.start),),
            )
        ]
    )
    piped.queue.pipelines.catalog = piped.queue.catalog
    await drain(piped)
    root, _, marks = await snapshot(piped, run_id)
    assert root["state"] == "version_blocked" and marks == {"choose": 1}
    await resume(piped.database, piped.catalog, run_id, accept_schema=True)
    await drain(piped)
    assert (await snapshot(piped, run_id))[0]["state"] == "succeeded"


async def test_queued_cycle_and_organizations(piped: Services) -> None:
    from shared.modules.catalog import Catalog

    queued = replace(pipeline, overlap="queue")
    newer = replace(
        module,
        pipelines=(queued,),
        schedules=(replace(module.schedules[0], contract=queued.start),),
    )
    piped.queue.catalog = piped.runtime.catalog = Catalog([newer])
    piped.queue.pipelines.catalog = piped.queue.catalog
    first = await start(piped, "first")
    second = await start(piped, "second")
    assert (await snapshot(piped, second))[0]["state"] == "queued"
    data = pipeline.start.input(request=StartRequest[Ref](data=Ref(), cycle_key="first"))
    other = await piped.runtime.submit(pipeline.start, data, caller=replace(CALLER, org_id="org-b"))
    assert other != first and (await snapshot(piped, other))[0]["state"] == "running"
    await drain(piped)
    for item in (first, second, other):
        assert (await snapshot(piped, item))[0]["state"] == "succeeded"
