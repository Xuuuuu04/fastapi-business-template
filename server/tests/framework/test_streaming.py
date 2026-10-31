import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.setup.build import Services, build
from app.setup.web import create_app
from shared.access.caller import SYSTEM
from shared.flow.streaming import stream_events
from shared.modules.catalog import Catalog
from shared.public import Data, Emitter, Flow, Module, Nothing, WorkData, contract, meaning, step
from tests.framework.sample_modules import NoteStore, notes, sample_metadata
from tests.testing_app import KEY, READER, make_settings, reset_database_now


class StreamResult(Data):
    saved: int = meaning("保存后的记录数")


class StreamWork(WorkData):
    result: StreamResult = meaning("操作结果")


stream_contract = contract(
    "stream_probe.run",
    "流式测试",
    input=Nothing,
    output=StreamResult,
    access="stream_probe.use",
    stream=True,
    effect="command",
)


def probe_module(gate: asyncio.Event, *, full: asyncio.Event | None = None) -> Module:
    @step("写入并输出", writes=["result"], saves=True)
    async def save_stream(data: StreamWork, store: NoteStore, emit: Emitter) -> None:
        saved = await store.add("stream")
        await emit("part")
        if full is not None:
            for index in range(100):
                if index == 15:
                    full.set()
                await emit(str(index))
        await gate.wait()
        data.result = StreamResult(saved=saved)

    flow = Flow("流式测试", work=StreamWork, result="result", steps=[save_stream])
    return Module(
        "stream_probe", "流式测试", "1", {stream_contract: flow}, store=NoteStore, kind="capability"
    )


async def prepare(services: Services, gate: asyncio.Event) -> None:
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
    services.runtime.catalog = Catalog([probe_module(gate)])


async def committed_count(services: Services) -> int:
    async with services.database.read() as connection:
        return int(await connection.scalar(select(func.count()).select_from(notes)))


@pytest.mark.anyio
async def test_stream_completion(services: Services) -> None:
    gate = asyncio.Event()
    await prepare(services, gate)
    stream = services.runtime.stream(stream_contract, Nothing(), caller=SYSTEM)
    start = await anext(stream)
    assert b"event: start" in start
    assert b"event: chunk" in await anext(stream)
    gate.set()
    done = await anext(stream)
    assert b"event: done" in done
    assert json.loads(done.split(b"data: ")[1])["saved"] == 1
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert await committed_count(services) == 1


@pytest.mark.anyio
async def test_stream_disconnect_rolls_back(services: Services) -> None:
    gate = asyncio.Event()
    await prepare(services, gate)
    stream = services.runtime.stream(stream_contract, Nothing(), caller=SYSTEM)
    start = await anext(stream)
    assert b"event: chunk" in await anext(stream)
    await stream.aclose()
    assert await committed_count(services) == 0
    run_id = json.loads(start.split(b"data: ")[1])
    recorded = await services.recorder.get(run_id)
    assert recorded is not None
    assert recorded.status == "failed" and recorded.error_code == "cancelled"


@pytest.mark.anyio
async def test_full_stream_disconnect_rolls_back(services: Services) -> None:
    gate, full = asyncio.Event(), asyncio.Event()
    await prepare(services, gate)
    services.runtime.catalog = Catalog([probe_module(gate, full=full)])
    stream = stream_events(
        services.runtime, stream_contract, Nothing(), caller=SYSTEM, request_id=""
    )
    start = await anext(stream)
    await asyncio.wait_for(full.wait(), 1)
    await asyncio.wait_for(stream.aclose(), 1)
    assert await committed_count(services) == 0
    run_id = json.loads(start.split(b"data: ")[1])
    recorded = await services.recorder.get(run_id)
    assert recorded is not None
    assert recorded.status == "failed" and recorded.error_code == "cancelled"


@pytest.mark.anyio
async def test_stream_error_is_reported(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failed(*args: object, **kwargs: object) -> Nothing:
        raise ValueError("不能暴露给客户端的内部细节")

    monkeypatch.setattr(services.runtime, "run", failed)
    events = [
        event
        async for event in stream_events(
            services.runtime, stream_contract, Nothing(), caller=SYSTEM, request_id=""
        )
    ]
    assert len(events) == 1 and events[0].startswith(b"event: error\n")
    problem = json.loads(events[0].split(b"data: ")[1])
    assert problem == {
        "code": "internal_error",
        "message": "服务器内部错误，请用运行编号查询排查信息",
        "run_id": "",
    }


class Topic(Data):
    topic: str = meaning("主题", min_length=1)


class TalkWork(WorkData):
    topic: str = meaning("主题")
    result: StreamResult = meaning("操作结果")


talk_contract = contract(
    "talk_probe.talk",
    "流式讲解",
    input=Topic,
    output=StreamResult,
    access="talk_probe.use",
    stream=True,
    effect="command",
)


@step("分段讲解", reads=["topic"], writes=["result"])
async def talk(data: TalkWork, emit: Emitter) -> None:
    await emit(data.topic)
    await emit("完")
    data.result = StreamResult(saved=0)


talk_module = Module(
    "talk_probe",
    "流式讲解",
    "1",
    {talk_contract: Flow("流式讲解", work=TalkWork, result="result", steps=[talk])},
    kind="capability",
)


def test_stream_http_entry(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    reset_database_now(settings.database_url)
    app = create_app(settings, build(settings, modules=[talk_module]))
    with TestClient(app) as client:
        url = "/api/v1/stream/talk_probe.talk"
        assert client.post(url, json={"topic": "价格"}).status_code == 401
        assert client.post(url, json={"topic": "价格"}, headers=READER).status_code == 403
        assert client.post(url, json={"topic": ""}, headers=KEY).status_code == 422
        assert client.post("/api/v1/stream/none.x", json={}, headers=KEY).status_code == 404
        reply = client.post(url, json={"topic": "价格"}, headers=KEY)
        assert reply.status_code == 200
        assert reply.headers["content-type"].startswith("text/event-stream")
        events = [block.split("\n")[0] for block in reply.text.strip().split("\n\n")]
        assert events == ["event: start", "event: chunk", "event: chunk", "event: done"]
        assert 'data: "价格"' in reply.text
