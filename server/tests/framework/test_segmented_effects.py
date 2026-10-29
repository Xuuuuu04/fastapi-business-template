import asyncio
import time
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import select, update

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.jobs.tables import checkpoints, jobs
from shared.jobs.views import get_job
from shared.jobs.worker import Worker, WorkerOptions
from shared.public import Checkpoint, Flow, JobPlan, Module, Retry, step
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.service import RemoteService
from tests.framework.test_remote_write_safety import (
    Input,
    Work,
    child,
    fail,
    partner,
    run,
    send,
    write,
)
from tests.testing_app import make_settings, prepare_test_database

pytestmark = pytest.mark.anyio


@step("声明本批结束")
def declare_batch(data: Work, checkpoint: Checkpoint) -> None:
    checkpoint.finish(rows=1)


def effect_module(nested: bool, fails: bool) -> Module:
    return Module(
        "effect_probe",
        "分段外部效果检查",
        "1",
        {
            write: Flow("子流程", work=Work, result="result", steps=[send]),
            run: Flow(
                "分段外部效果",
                work=Work,
                result="result",
                steps=[declare_batch, child if nested else send, *([fail] if fails else [])],
            ),
        },
        remotes=(partner,),
        jobs=(JobPlan(run, retry=Retry(2, (0,)), segmented=True, repeat_safe=True),),
    )


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("method,state", [("GET", "waiting_retry"), ("POST", "unknown")])
async def test_segmented_external_failure(tmp_path: Path, nested, method, state) -> None:
    settings = make_settings(tmp_path)
    await prepare_test_database(settings.database_url)
    services = build(settings, modules=[effect_module(nested, True)])
    calls = []

    def reply(request):
        calls.append(request.method)
        return httpx2.Response(200, json={"saved": True})

    services.runtime.remotes = RemoteService(
        {partner.name: RemoteConfig(base_url="https://synthetic.test")},
        {partner.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    try:
        job_id = await services.runtime.submit(run, Input(method=method), caller=SYSTEM)
        ticket = await services.queue.claim(time.time())
        await Worker(services.runtime, services.queue, [], WorkerOptions()).execute(ticket)
        job = await get_job(services.database, job_id)
        assert job is not None and job.state == state and calls == [method]
        if method == "POST":
            assert await services.queue.claim(time.time()) is None
    finally:
        await services.close()


async def test_external_intent_survives_interrupted_attempt(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    await prepare_test_database(settings.database_url)
    services = build(settings, modules=[effect_module(True, False)])
    sent = asyncio.Event()

    async def reply(request):
        sent.set()
        await asyncio.Event().wait()
        return httpx2.Response(200)

    services.runtime.remotes = RemoteService(
        {partner.name: RemoteConfig(base_url="https://synthetic.test")},
        {partner.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    try:
        job_id = await services.runtime.submit(run, Input(method="POST"), caller=SYSTEM)
        ticket = await services.queue.claim(time.time())
        worker = Worker(services.runtime, services.queue, [], WorkerOptions())
        running = asyncio.create_task(worker.execute(ticket))
        await asyncio.wait_for(sent.wait(), 5)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        async with services.database.write() as connection:
            assert await connection.scalar(select(checkpoints.c.external_pending)) is True
            await connection.execute(update(jobs).values(lease_until=time.time() - 1))
        assert await services.queue.reclaim(time.time()) == 1
        job = await get_job(services.database, job_id)
        assert job is not None and job.state == "unknown"
        assert await services.queue.claim(time.time()) is None
    finally:
        await services.close()
