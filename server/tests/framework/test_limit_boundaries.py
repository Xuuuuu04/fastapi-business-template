import asyncio
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from shared.access.caller import SYSTEM
from shared.effects.smtp import MailInput, SmtpAdapter, SmtpConfig
from shared.effects.spec import AdapterReply
from shared.errors.framework import StepRuleBroken
from shared.jobs.limits import ResourceLimit, SerialKey, limit_problems
from shared.jobs.resources import reconfigure
from tests.framework.test_job_limits import Input, operation, setup

pytestmark = pytest.mark.anyio


async def test_resource_reconfiguration_requires_idle(tmp_path: Path) -> None:
    services, _, clock = await setup(tmp_path)
    try:
        await services.runtime.submit(
            operation, Input(session="s", expires=datetime.fromtimestamp(1000, UTC)), caller=SYSTEM
        )
        ticket = await services.queue.claim(clock.now())
        assert ticket is not None
        with pytest.raises(StepRuleBroken, match="在途"):
            async with services.database.write() as connection:
                await reconfigure(connection, ResourceLimit("supplier", 3), clock.now())
        await services.queue.fail(ticket, "failed", "synthetic", "合成结束")
        async with services.database.write() as connection:
            await reconfigure(connection, ResourceLimit("supplier", 3), clock.now())
        from shared.jobs.resource_tables import pools

        async with services.database.read() as connection:
            assert await connection.scalar(select(pools.c.capacity)) == 3
    finally:
        await services.close()


async def test_nested_missing_serial_field_is_rejected(tmp_path: Path) -> None:
    services, _, _ = await setup(tmp_path)
    try:
        plan = services.catalog.plan(operation.name)
        assert plan is not None
        bad = replace(plan, serial=SerialKey("conversation", "session.missing"))
        assert any("session.missing" in issue for issue in limit_problems(bad))
    finally:
        await services.close()


async def test_smtp_cancellation_keeps_actual_thread_limit(monkeypatch) -> None:
    started, release = threading.Event(), threading.Event()
    adapter = SmtpAdapter(SmtpConfig(account="test", host="synthetic.invalid"))
    adapter.configure_limit(1)
    calls = 0

    def send_once(input, key):
        nonlocal calls
        calls += 1
        started.set()
        release.wait(5)
        return AdapterReply("unknown")

    monkeypatch.setattr(adapter, "send_once", send_once)
    input = MailInput(
        sender="s@example.invalid", recipient="r@example.invalid", subject="test", text="body"
    )
    first = asyncio.create_task(adapter.send(input, "one"))
    await asyncio.to_thread(started.wait, 2)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(adapter.send(input, "two"))
    try:
        await asyncio.sleep(0)
        assert calls == 1 and len(adapter.work.running) == 1
        release.set()
        await second
        assert calls == 2
    finally:
        release.set()
        second.cancel()
        await adapter.close()
