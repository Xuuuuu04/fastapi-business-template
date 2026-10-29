import asyncio
import time
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import update

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.errors.framework import ResultUnknown
from shared.jobs.tables import jobs
from shared.jobs.views import get_job
from shared.records.stores import RunFilter
from tests.framework.sample_modules import CalcInput, SlowInput, calc, slow
from tests.framework.test_jobs import make_worker

pytestmark = pytest.mark.anyio


class CommitLost:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def commit(self) -> None:
        raise ConnectionResetError("提交时连接断开")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)


async def test_commit_lost_is_unknown(sample: Services, monkeypatch: pytest.MonkeyPatch) -> None:
    real = sample.database.open_write

    async def open_broken() -> Any:
        return CommitLost(await real())

    monkeypatch.setattr(sample.database, "open_write", open_broken)
    with pytest.raises(ResultUnknown):
        await sample.runtime.run(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    assert run.writes == "unknown" and "保存结果尚不能确认" in run.summary


async def test_worker_stop_leaves_job_for_recovery(sample: Services) -> None:
    job_id = await sample.runtime.submit(slow, SlowInput(seconds=5, mark="x"), caller=DEVELOPER)
    worker = make_worker(sample)
    worker.options.shutdown_seconds = 0.05
    stop = asyncio.Event()
    running = asyncio.create_task(worker.run(stop))
    for _ in range(50):
        if (job := await get_job(sample.database, job_id)) and job.state == "running":
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(running, 2)
    assert (job := await get_job(sample.database, job_id)) and job.state == "running"
    await asyncio.sleep(0.35)
    assert await sample.queue.reclaim(time.time()) == 1
    assert (job := await get_job(sample.database, job_id)) and job.state == "waiting_retry"


async def test_same_key_after_version_change(sample: Services) -> None:
    first = await sample.runtime.submit(
        calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER, key="order-7"
    )
    async with sample.database.write() as connection:
        await connection.execute(update(jobs).values(module_version="0"))
    again = await sample.runtime.submit(
        calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER, key="order-7"
    )
    assert again == first
