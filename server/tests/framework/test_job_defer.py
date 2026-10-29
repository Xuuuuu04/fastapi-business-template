from pathlib import Path

import pytest
from sqlalchemy import select

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.application.spec import ApplicationSpec
from shared.errors.framework import RemoteUnavailable
from shared.flow.testing import FakeClock
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.public import (
    Flow,
    JobPlan,
    Module,
    Nothing,
    ResourceLimit,
    Retry,
    RetryLater,
    WorkData,
    contract,
    meaning,
    step,
)
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


class Work(WorkData):
    result: Nothing = meaning("完成结果")


def deferred_module() -> Module:
    count = 0
    operation = contract(
        "defer_probe.run",
        "延后处理",
        input=Nothing,
        output=Nothing,
        access="public",
        effect="command",
    )

    @step("尝试合成处理", writes=["result"])
    def work(data: Work) -> None:
        nonlocal count
        count += 1
        if count <= 2:
            raise RetryLater(10, resource="model", detail="合成429冷却")
        if count == 3:
            raise RemoteUnavailable("合成暂时失败")
        data.result = Nothing()

    return Module(
        "defer_probe",
        "延后处理",
        "1",
        {operation: Flow("合成处理", work=Work, result="result", steps=[work])},
        jobs=(JobPlan(operation, retry=Retry(1, (0,)), resources=(ResourceLimit("model"),)),),
        kind="capability",
    )


async def test_deferred_attempts_do_not_consume_retry_budget(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    clock, module = FakeClock(100), deferred_module()
    operation = next(iter(module.provides))
    services = build(settings, modules=[module], application=ApplicationSpec(clock=clock))
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    try:
        id = await services.runtime.submit(operation, Nothing(), caller=SYSTEM)
        for index in range(4):
            ticket = await services.queue.claim(clock.now())
            assert ticket is not None
            await worker.execute(ticket)
            if index < 2:
                assert await services.queue.claim(clock.now()) is None
                clock.advance(10)
        async with services.database.read() as connection:
            row = (await connection.execute(select(jobs).where(jobs.c.id == id))).mappings().one()
        assert row["state"] == "done" and row["attempt"] == 4 and row["failed_attempts"] == 1
    finally:
        await services.close()
