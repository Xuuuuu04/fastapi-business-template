"""
流式操作在完成时提交写入，在客户端断开时取消并回滚写入。
"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.setup.build import Services, build
from app.setup.web import create_app
from shared.access.caller import SYSTEM
from shared.modules.catalog import Catalog
from shared.public import Data, Emitter, Flow, Module, Nothing, WorkData, contract, meaning, step
from tests.framework.sample_modules import NoteStore, notes, sample_metadata
from tests.testing_app import KEY, READER, make_settings, reset_database_now


# 流式输出测试返回的已保存记录数。
class StreamResult(Data):
    saved: int = meaning("保存后的记录数")


# 流式输出测试各步骤共享的执行结果。
class StreamWork(WorkData):
    result: StreamResult = meaning("操作结果")


stream_contract = contract(
    "stream_probe.run",
    "流式测试",
    input=Nothing,
    output=StreamResult,
    access="stream_probe.use",
    stream=True,
)


# 创建一个先写数据库、再输出分段并等待继续的流式模块。
def probe_module(gate: asyncio.Event) -> Module:
    # 写入未提交的记录，发出分段后等待测试放行。
    @step("写入并输出", writes=["result"], saves=True)
    async def save_stream(data: StreamWork, store: NoteStore, emit: Emitter) -> None:
        saved = await store.add("stream")
        await emit("part")
        await gate.wait()
        data.result = StreamResult(saved=saved)

    flow = Flow("流式测试", work=StreamWork, result="result", steps=[save_stream])
    return Module("stream_probe", "流式测试", "1", {stream_contract: flow}, store=NoteStore)


# 在测试数据库中建立流式模块写入的表。
async def prepare(services: Services, gate: asyncio.Event) -> None:
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
    services.runtime.catalog = Catalog([probe_module(gate)])


# 返回目前已提交的测试记录数。
async def committed_count(services: Services) -> int:
    async with services.database.read() as connection:
        return int(await connection.scalar(select(func.count()).select_from(notes)))


# 正常读完流会得到开始、分段和完成事件，并提交数据库写入。
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


# 客户端只读一段便断开时，运行被取消，未提交的写入撤销。
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


# 流式大模型测试接收的主题。
class Topic(Data):
    topic: str = meaning("主题", min_length=1)


# 流式大模型测试各步骤共享的主题和执行结果。
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
)


# 不访问数据库，只把主题分两段输出。
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
)


# HTTP 入口在开始输出前检查操作、权限和输入，成功时按 SSE 返回全部事件。
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
