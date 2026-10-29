import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.setup.build import build
from shared.access.caller import SYSTEM, Caller
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.public import (
    ApplicationSpec,
    Clock,
    FakeClock,
    Flow,
    JobPlan,
    Module,
    Nothing,
    Validity,
    WorkData,
    contract,
    meaning,
    step,
)
from tests.framework.test_job_limits import Input, operation, setup
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


async def test_org_scoped_keys_and_legacy_unknown_reuse(tmp_path: Path) -> None:
    services, _, _ = await setup(tmp_path)
    first = Caller("same-user", "user", "用户", org_id="a")
    other = Caller("same-user", "user", "用户", org_id="b")
    input = Input(session="s", expires=datetime.fromtimestamp(1000, UTC))
    try:
        id = await services.runtime.submit(operation, input, caller=first, key="once")
        second = await services.runtime.submit(operation, input, caller=other, key="once")
        assert id != second
        async with services.database.write() as connection:
            await connection.execute(
                jobs.update().where(jobs.c.id == id).values(key_scope=first.id, state="unknown")
            )
        reused = await services.runtime.submit(operation, input, caller=first, key="once")
        assert reused == id
        assert await services.runtime.submit(operation, input, caller=other, key="once") == second
    finally:
        await services.close()


class CheckWork(WorkData):
    session: str = meaning("会话")
    expires: datetime = meaning("有效期")
    result: Validity = meaning("核对结果")


class RunWork(WorkData):
    session: str = meaning("会话")
    expires: datetime = meaning("有效期")
    result: Nothing = meaning("业务结果")


def deadline_module(checking: asyncio.Event, working: asyncio.Event) -> Module:
    @step("核对状态", writes=["result"])
    async def check(data: CheckWork, clock: Clock) -> None:
        checking.set()
        await clock.sleep(4)
        data.result = Validity(valid=True)

    @step("处理业务", writes=["result"])
    async def work(data: RunWork, clock: Clock) -> None:
        working.set()
        await clock.sleep(4)
        data.result = Nothing()

    query = contract(
        "limit_probe.check",
        "执行前核对",
        input=Input,
        output=Validity,
        access="public",
        effect="query",
        timeout=10,
    )
    return Module(
        "limit_probe",
        "预算核对",
        "1",
        {
            query: Flow("核对", work=CheckWork, result="result", steps=[check]),
            operation: Flow("业务", work=RunWork, result="result", steps=[work]),
        },
        jobs=(JobPlan(operation, revalidate=query, attempt_timeout=5),),
        kind="capability",
    )


async def test_revalidation_and_work_share_attempt_deadline(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    clock = FakeClock(100)
    checking, working = asyncio.Event(), asyncio.Event()

    module = deadline_module(checking, working)
    services = build(settings, modules=[module], application=ApplicationSpec(clock=clock))
    id = await services.runtime.submit(
        operation, Input(session="s", expires=datetime.fromtimestamp(1000, UTC)), caller=SYSTEM
    )
    ticket = await services.queue.claim(clock.now())
    assert ticket is not None
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    running = asyncio.create_task(worker.execute(ticket))
    try:
        await checking.wait()
        await asyncio.sleep(0)
        clock.advance(4)
        await working.wait()
        await asyncio.sleep(0)
        clock.advance(1)
        await running
        async with services.database.read() as connection:
            row = (await connection.execute(select(jobs).where(jobs.c.id == id))).mappings().one()
        assert row["state"] == "failed" and row["error_code"] == "run_timeout"
    finally:
        running.cancel()
        await services.close()
