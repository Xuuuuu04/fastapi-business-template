import asyncio
import time
from decimal import Decimal

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from tests.framework.sample_modules import CalcInput, calc
from tests.framework.test_jobs import make_worker

pytestmark = pytest.mark.anyio


async def test_worker_drain_waits_for_cancelled_cleanup(sample: Services) -> None:
    worker = make_worker(sample)
    worker.options.shutdown_seconds = 0
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def running() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    task = asyncio.create_task(running())
    worker.tasks.add(task)
    task.add_done_callback(worker.tasks.discard)
    await started.wait()
    draining = asyncio.create_task(worker.drain())
    try:
        await asyncio.wait_for(cleaning.wait(), 1)
        assert not draining.done() and not cleaned.is_set()
        release.set()
        await asyncio.wait_for(draining, 1)
        assert task.cancelled() and cleaned.is_set() and not worker.tasks
    finally:
        release.set()
        await asyncio.gather(task, draining, return_exceptions=True)


async def test_worker_drain_keeps_completed_task(sample: Services) -> None:
    worker = make_worker(sample)
    release = asyncio.Event()

    async def running() -> None:
        await release.wait()

    task = asyncio.create_task(running())
    worker.tasks.add(task)
    draining = asyncio.create_task(worker.drain())
    release.set()
    await asyncio.wait_for(draining, 1)
    assert task.done() and not task.cancelled() and task.result() is None


async def test_worker_drain_reports_error_after_cleanup(sample: Services) -> None:
    worker = make_worker(sample)
    worker.options.shutdown_seconds = 0
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def failed() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            raise RuntimeError("清理失败")

    async def running() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    tasks = [asyncio.create_task(failed()), asyncio.create_task(running())]
    worker.tasks.update(tasks)
    await started.wait()
    draining = asyncio.create_task(worker.drain())
    try:
        await asyncio.wait_for(cleaning.wait(), 1)
        assert not draining.done()
        release.set()
        with pytest.raises(RuntimeError, match="清理失败"):
            await asyncio.wait_for(draining, 1)
        assert cleaned.is_set() and all(task.done() for task in tasks)
    finally:
        release.set()
        await asyncio.gather(*tasks, draining, return_exceptions=True)


async def test_worker_execute_waits_for_heartbeat_cleanup(
    sample: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    ticket = await sample.queue.claim(time.time())
    assert ticket is not None
    worker = make_worker(sample)
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def keep_lease(*args: object) -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    async def run_job(*args: object) -> None:
        await started.wait()

    monkeypatch.setattr(worker, "keep_lease", keep_lease)
    monkeypatch.setattr(worker, "run_job", run_job)
    await worker.execute(ticket)
    assert cleaned.is_set()
