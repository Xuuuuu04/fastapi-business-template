from pathlib import Path

import httpx2
import pytest

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.errors.framework import RemoteResultUnknown, RemoteUnavailable
from shared.jobs.views import get_job
from shared.jobs.worker import Worker, WorkerOptions, next_state
from shared.model_calls.providers import FakeModel
from shared.public import (
    Call,
    Data,
    Endpoint,
    Flow,
    JobPlan,
    Module,
    Nothing,
    RemoteClient,
    Retry,
    WorkData,
    contract,
    meaning,
    remote,
    step,
)
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.service import RemoteRequest, RemoteService
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio
partner = remote("write_probe", "合成写入服务", retries=1)


class Input(Data):
    method: str = meaning("GET 或 POST")


class Work(WorkData):
    method: str = meaning("外部调用方法")
    result: Nothing = meaning("空结果")


class Saved(Data):
    saved: bool = meaning("对方是否已保存")


read_record = Endpoint(
    "write_probe.read", "GET", "/record", input=Nothing, output=Saved, effect="read"
)
write_record = Endpoint(
    "write_probe.write", "POST", "/record", input=Nothing, output=Saved, effect="write"
)
write = contract(
    "effect_probe.write", "调用外部系统", input=Input, output=Nothing, access="public", entry=False
)
run = contract("effect_probe.run", "调用后失败", input=Input, output=Nothing, access="public")


@step(
    "请求合成服务",
    reads=["method"],
    writes=["result"],
    remotes=[partner],
    endpoints=[read_record, write_record],
)
async def send(data: Work, remote: RemoteClient) -> None:
    if data.method == "GET":
        await remote.call(partner, read_record, Nothing())
    else:
        await remote.call(partner, write_record, Nothing(), key="synthetic-stable-key")
    data.result = Nothing()


@step("调用子流程", reads=["method"], writes=["result"], uses=[write])
async def child(data: Work, call: Call) -> None:
    data.result = await call(write, Input(method=data.method))


@step("后续失败")
def fail(data: Work) -> None:
    raise RemoteUnavailable("合成的后续暂时故障")


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("method,expected", [("GET", "waiting_retry"), ("POST", "unknown")])
async def test_job_does_not_replay_external_effect(
    tmp_path: Path, nested: bool, method: str, expected: str
) -> None:
    steps = [child if nested else send, fail]
    module = Module(
        "effect_probe",
        "外部效果检查",
        "1",
        {
            write: Flow("子流程", work=Work, result="result", steps=[send]),
            run: Flow("失败流程", work=Work, result="result", steps=steps),
        },
        remotes=(partner,),
        endpoints=(read_record, write_record),
        jobs=(JobPlan(run, retry=Retry(1, (0,))),),
    )
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    services = build(settings, modules=[module], provider=FakeModel())
    seen: list[str] = []

    def reply(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.method)
        return httpx2.Response(200, json={"saved": True})

    services.runtime.remotes = RemoteService(
        {partner.name: RemoteConfig(base_url="https://synthetic.test")},
        {partner.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    try:
        job_id = await services.runtime.submit(run, Input(method=method), caller=SYSTEM)
        ticket = await services.queue.claim(10**12)
        assert ticket is not None
        worker = Worker(services.runtime, services.queue, [], WorkerOptions())
        await worker.execute(ticket)
        job = await get_job(services.database, job_id)
        assert job is not None and job.state == expected
        assert seen == [method]
        if method == "POST":
            assert job.error_code == "remote_result_unknown"
            assert await services.queue.claim(10**12) is None
    finally:
        await services.close()


@pytest.mark.parametrize("status", [408, 499, 500, 503])
async def test_unkeyed_failed_write_stays_unknown(status: int) -> None:
    calls = []

    def reply(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(status)

    service = RemoteService(
        {partner.name: RemoteConfig(base_url="https://synthetic.test")},
        {partner.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    try:
        with pytest.raises(RemoteResultUnknown) as caught:
            await service.send(
                partner, RemoteRequest("POST", "/record", "write_probe.write", "write"), []
            )
        assert len(calls) == 1
        assert next_state(caught.value.kind, 1, 3, lambda _: 0)[0] == "unknown"
    finally:
        await service.close()


@pytest.mark.parametrize("last", ["connection", "rejected"])
async def test_later_known_failure_cannot_erase_earlier_unknown(last: str) -> None:
    calls = 0

    def reply(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(503)
        if last == "connection":
            raise httpx2.ConnectError("synthetic connection refusal")
        return httpx2.Response(401)

    service = RemoteService(
        {partner.name: RemoteConfig(base_url="https://synthetic.test")},
        {partner.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.send(
                partner,
                RemoteRequest("POST", "/record", "write_probe.write", "write", key="stable"),
                [],
            )
        assert calls == 2
    finally:
        await service.close()
