import asyncio
from pathlib import Path

import pytest

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.errors.framework import RunTimeout
from shared.public import (
    ApplicationSpec,
    Clock,
    FakeClock,
    Flow,
    JobPlan,
    Module,
    Nothing,
    WorkData,
    contract,
    meaning,
    step,
)
from shared.records.stores import RunFilter
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


class Work(WorkData):
    result: Nothing = meaning("执行结果")


async def test_runtime_deadline_and_elapsed_use_same_clock(tmp_path: Path) -> None:
    clock = FakeClock(100)
    entered = asyncio.Event()

    @step("受控等待", writes=["result"])
    async def wait(data: Work, clock: Clock) -> None:
        entered.set()
        await clock.sleep(30)
        data.result = Nothing()

    operation = contract(
        "clock_probe.wait",
        "等待",
        input=Nothing,
        output=Nothing,
        access="public",
        timeout=5,
        effect="query",
    )
    module = Module(
        "clock_probe",
        "受控时间",
        "1",
        {operation: Flow("等待", work=Work, result="result", steps=[wait])},
        kind="capability",
    )
    services = build(
        make_settings(tmp_path), modules=[module], application=ApplicationSpec(clock=clock)
    )
    running = asyncio.create_task(services.runtime.run(operation, Nothing(), caller=SYSTEM))
    try:
        await entered.wait()
        await asyncio.sleep(0)
        clock.advance(1)
        clock.set_wall(50)
        clock.advance(4)
        with pytest.raises(RunTimeout):
            await running
        [record] = await services.recorder.store.recent(RunFilter(), 10)
        assert record.started_at == 100 and record.ended_at == 54
        assert record.elapsed_ms == 5000 and record.steps[0].elapsed_ms == 5000
        assert not clock.waiters
    finally:
        running.cancel()
        await services.close()


async def test_queue_uses_product_clock_without_runtime_context(tmp_path: Path) -> None:
    clock = FakeClock(100)

    @step("空结果", writes=["result"])
    def result(data: Work) -> None:
        data.result = Nothing()

    operation = contract(
        "clock_probe.run",
        "空任务",
        input=Nothing,
        output=Nothing,
        access="public",
        effect="command",
    )
    module = Module(
        "clock_probe",
        "受控时间",
        "1",
        {operation: Flow("空任务", work=Work, result="result", steps=[result])},
        jobs=(JobPlan(operation),),
        kind="capability",
    )
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    services = build(settings, modules=[module], application=ApplicationSpec(clock=clock))
    try:
        id = await services.runtime.submit(operation, Nothing(), caller=SYSTEM)
        from sqlalchemy import select

        from shared.jobs.tables import jobs

        async with services.database.read() as connection:
            row = (await connection.execute(select(jobs).where(jobs.c.id == id))).mappings().one()
        assert row["created_at"] == row["run_after"] == 100
        ticket = await services.queue.claim(clock.now())
        assert ticket is not None
    finally:
        await services.close()
