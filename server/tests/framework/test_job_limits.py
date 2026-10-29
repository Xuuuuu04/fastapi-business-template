import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.application.spec import ApplicationSpec
from shared.flow.testing import FakeClock
from shared.jobs.queue import JobQueue
from shared.jobs.resource_tables import leases
from shared.jobs.tables import jobs
from shared.public import (
    Data,
    Flow,
    JobPlan,
    Module,
    Nothing,
    ResourceLimit,
    SerialKey,
    WorkData,
    contract,
    meaning,
    step,
)
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


class Input(Data):
    session: str = meaning("会话业务键")
    expires: datetime = meaning("业务有效期，带时区")


class Work(WorkData):
    session: str = meaning("会话业务键")
    expires: datetime = meaning("业务有效期")
    result: Nothing = meaning("执行结果")


@step("空结果", writes=["result"])
def finish(data: Work) -> None:
    data.result = Nothing()


operation = contract(
    "limit_probe.run", "受限任务", input=Input, output=Nothing, access="public", effect="command"
)


async def setup(tmp_path: Path, *, serial=False, concurrency=2, cooldown=0, timeout=None):
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    clock = FakeClock(100)
    plan = JobPlan(
        operation,
        serial=SerialKey("conversation", "session") if serial else None,
        resources=(ResourceLimit("supplier", concurrency, cooldown),),
        queue_timeout=timeout,
        valid_until_field="expires",
    )
    module = Module(
        "limit_probe",
        "合成约束",
        "1",
        {operation: Flow("空任务", work=Work, result="result", steps=[finish])},
        jobs=(plan,),
        kind="capability",
    )
    services = build(settings, modules=[module], application=ApplicationSpec(clock=clock))
    second = JobQueue(services.catalog, services.database)
    second.clock = clock
    return services, second, clock


async def test_serial_order_and_cross_worker_capacity(tmp_path: Path) -> None:
    services, other, clock = await setup(tmp_path, serial=True)

    def request(session: str) -> Input:
        return Input(session=session, expires=datetime.fromtimestamp(1000, UTC))

    try:
        first = await services.runtime.submit(operation, request("a"), caller=SYSTEM)
        second = await services.runtime.submit(operation, request("a"), caller=SYSTEM)
        independent = await services.runtime.submit(operation, request("b"), caller=SYSTEM)
        taken = await asyncio.gather(services.queue.claim(clock.now()), other.claim(clock.now()))
        assert {ticket.id for ticket in taken if ticket} == {first, independent}
        assert await other.claim(clock.now()) is None
        ticket = next(ticket for ticket in taken if ticket and ticket.id == first)
        async with services.database.write() as connection:
            assert await services.queue.finish(connection, ticket, "{}", "run")
        next_ticket = await other.claim(clock.now())
        assert next_ticket is not None and next_ticket.id == second
    finally:
        await services.close()


async def test_unknown_key_stops_later_jobs(tmp_path: Path) -> None:
    services, other, clock = await setup(tmp_path, serial=True)
    input = Input(session="a", expires=datetime.fromtimestamp(1000, UTC))
    try:
        first = await services.runtime.submit(operation, input, caller=SYSTEM)
        await services.runtime.submit(operation, input, caller=SYSTEM)
        ticket = await services.queue.claim(clock.now())
        assert ticket is not None and ticket.id == first
        assert await services.queue.fail(ticket, "unknown", "lost_reply", "合成未知回执")
        assert await other.claim(clock.now()) is None
        async with services.database.read() as connection:
            assert await connection.scalar(select(func.count()).select_from(leases)) == 0
    finally:
        await services.close()


async def test_cooldown_and_queue_expiry_release_slots(tmp_path: Path) -> None:
    services, other, clock = await setup(tmp_path, concurrency=1, cooldown=10, timeout=5)
    input = Input(session="a", expires=datetime.fromtimestamp(1000, UTC))
    try:
        first = await services.runtime.submit(operation, input, caller=SYSTEM)
        pending = await services.runtime.submit(operation, input, caller=SYSTEM)
        ticket = await services.queue.claim(clock.now())
        assert ticket is not None
        first, pending = ticket.id, pending if ticket.id == first else first
        await services.queue.fail(ticket, "waiting_retry", "temporary", "合成429", run_after=101)
        assert await other.claim(clock.now()) is None
        clock.advance(5)
        assert await other.claim(clock.now()) is None
        async with services.database.read() as connection:
            row = (
                (await connection.execute(select(jobs).where(jobs.c.id == pending)))
                .mappings()
                .one()
            )
            assert row["state"] == "expired" and row["error_message"] == "排队预算耗尽"
            assert await connection.scalar(select(func.count()).select_from(leases)) == 0
        clock.advance(5)
        resumed = await other.claim(clock.now())
        assert resumed is not None and resumed.id == first
    finally:
        await services.close()


async def test_business_expiry_and_stale_lease(tmp_path: Path) -> None:
    services, other, clock = await setup(tmp_path)
    try:
        expired = await services.runtime.submit(
            operation, Input(session="old", expires=datetime.fromtimestamp(99, UTC)), caller=SYSTEM
        )
        assert await other.claim(clock.now()) is None
        async with services.database.read() as connection:
            assert (
                await connection.scalar(select(jobs.c.state).where(jobs.c.id == expired))
                == "expired"
            )
        await services.runtime.submit(
            operation,
            Input(session="new", expires=datetime.fromtimestamp(1000, UTC)),
            caller=SYSTEM,
        )
        ticket = await services.queue.claim(clock.now())
        assert ticket is not None
        clock.advance(61)
        assert not await services.queue.extend(ticket, clock.now() + 60)
        async with services.database.write() as connection:
            assert not await services.queue.finish(connection, ticket, "{}", "late")
        await services.queue.reclaim(clock.now())
        async with services.database.read() as connection:
            assert await connection.scalar(select(func.count()).select_from(leases)) == 0
    finally:
        await services.close()
