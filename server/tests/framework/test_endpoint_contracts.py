"""
上游协议的运行、保护、启动检查和原件回放验证。
"""

import json
from dataclasses import replace
from pathlib import Path

import httpx2
import pytest
from fastapi_project.development.status import operation_status

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.drills.replay import Replay
from shared.errors.framework import DeclarationError, RemoteOutputInvalid, RemoteResultUnknown
from shared.graphs.observed import run_graph
from shared.graphs.static import flow_graph
from shared.model_calls.providers import FakeModel
from shared.modules.catalog import Catalog
from shared.modules.digest import digest_of
from shared.public import Flow
from shared.records.models import RemoteCallRecord, run_from_dict
from shared.remote_calls.gate import RemoteGate
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.service import RemoteRequest, RemoteService
from tests.framework.endpoint_sample import (
    Receipt,
    Request,
    module,
    read,
    read_endpoint,
    upstream,
    write,
    write_endpoint,
)
from tests.testing_app import make_settings, reset_database


# 同一组独立模块在当前测试数据库实际通过执行器运行。
@pytest.mark.anyio
@pytest.mark.parametrize("operation", [read, write])
async def test_typed_call_and_graphs(tmp_path: Path, operation: object) -> None:
    seen: list[httpx2.Request] = []

    # 保存收到的序列化请求，响应由框架校验成Data。
    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"accepted": True, "count": 2})

    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    services = build(settings, modules=[module], provider=FakeModel())
    services.runtime.remotes = service(respond)
    ids: list[str] = []
    try:
        result = await services.runtime.run(
            operation, Request(sku="x"), caller=SYSTEM, on_start=ids.append
        )
        assert result == Receipt(accepted=True, count=2)
        assert json.loads(seen[0].content) == {"sku": "x"}
        record = await services.recorder.get(ids[0])
        assert record is not None
        call = record.steps[0].remotes[0]
        assert call.endpoint in (read_endpoint.name, write_endpoint.name)
        assert call.outcome == "ok" and call.elapsed_ms >= 0
        assert call.endpoint in run_graph([record])
        assert call.endpoint in flow_graph(services.catalog.binding(operation))
        view = operation_status(services.catalog, operation.name, [])
        assert view["endpoints"][0]["name"] == call.endpoint
    finally:
        await services.close()


# 外部响应替身不依赖真实产品。
def service(respond: object) -> RemoteService:
    return RemoteService(
        {upstream.name: RemoteConfig(base_url="https://protocol.example")},
        {upstream.name: httpx2.MockTransport(respond)},
        retry_waits=(0,),
    )


# 字段错误只保存字段路径/错误类别，未知写入不丢失字段证据。
@pytest.mark.anyio
@pytest.mark.parametrize("operation", [read, write])
async def test_invalid_output_recorded(tmp_path: Path, operation: object) -> None:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    services = build(settings, modules=[module], provider=FakeModel())
    services.runtime.remotes = service(
        lambda request: httpx2.Response(200, json={"accepted": True, "count": "secret-value"})
    )
    ids: list[str] = []
    try:
        expected = RemoteOutputInvalid if operation is read else RemoteResultUnknown
        with pytest.raises(expected):
            await services.runtime.run(
                operation, Request(sku="x"), caller=SYSTEM, on_start=ids.append
            )
        run = await services.recorder.get(ids[0])
        assert run is not None
        call = run.steps[0].remotes[0]
        assert "count" in call.fields and "secret-value" not in str(run.to_dict())
        assert call.outcome == ("ok" if operation is read else "unknown")
        assert run_from_dict(run.to_dict()).steps[0].remotes[0].fields == call.fields
    finally:
        await services.close()


# HTTP未知状态与发送后超时写操作都只发一次。
@pytest.mark.anyio
@pytest.mark.parametrize("status", [202, 408, 499, 503, 0])
async def test_write_unknown(status: int) -> None:
    attempts = 0

    # 模拟对方已收到请求但回执不能确认。
    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if not status:
            raise httpx2.ReadTimeout("timeout", request=request)
        return httpx2.Response(status, json={"accepted": True, "count": 1})

    client = service(respond)
    records: list[RemoteCallRecord] = []
    effects: list[RemoteCallRecord] = []
    gate = RemoteGate(
        client, (upstream,), records, "测试", effects=effects, endpoints=(write_endpoint,)
    )
    try:
        with pytest.raises(RemoteResultUnknown):
            await gate.call(upstream, write_endpoint, Request(sku="x"))
        assert attempts == 1 and effects[0].outcome == "unknown"
    finally:
        await client.close()


# 确定拒绝保留已校验回执，拒绝响应坏格式也不会误报已写入。
@pytest.mark.anyio
@pytest.mark.parametrize("valid", [True, False])
async def test_refusal(valid: bool) -> None:
    client = service(
        lambda request: httpx2.Response(
            409, json={"accepted": False, "count": 0} if valid else {"accepted": False}
        )
    )
    records: list[RemoteCallRecord] = []
    gate = RemoteGate(client, (upstream,), records, "测试", endpoints=(write_endpoint,))
    try:
        if valid:
            reply = await gate.call(upstream, write_endpoint, Request(sku="x"))
            assert reply.status == 409 and not reply.data.accepted
        else:
            with pytest.raises(RemoteOutputInvalid):
                await gate.call(upstream, write_endpoint, Request(sku="x"))
        assert records[0].outcome == "failed"
    finally:
        await client.close()


# read效果的POST在暂时失败后可重试，write效果的GET禁止安全重试。
@pytest.mark.anyio
async def test_effect_overrides_method() -> None:
    calls = 0

    # 首次不可用，第二次响应成功。
    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(503 if calls == 1 else 200, json={"accepted": True, "count": 1})

    client = service(respond)
    try:
        gate = RemoteGate(client, (upstream,), [], "测试", endpoints=(read_endpoint,))
        await gate.call(upstream, read_endpoint, Request(sku="x"))
        assert calls == 2
        dangerous = replace(write_endpoint, method="GET")
        calls = 0
        gate = RemoteGate(client, (upstream,), [], "测试", endpoints=(dangerous,))
        with pytest.raises(RemoteResultUnknown):
            await gate.call(upstream, dangerous, Request(sku="x"))
        assert calls == 1
    finally:
        await client.close()


# 新声明缺失与不同对象重复定义均在启动发现；同一公开对象可以共享。
def test_startup_and_digest() -> None:
    with pytest.raises(DeclarationError, match="未在Module.endpoints登记"):
        Catalog([replace(module, endpoints=())])
    duplicate = replace(read_endpoint)
    with pytest.raises(DeclarationError, match="重复定义"):
        Catalog([replace(module, endpoints=(*module.endpoints, duplicate))])
    changed_step = replace(module.provides[read].steps[0], endpoints=())
    flow = Flow("漏声明", work=module.provides[read].work, result="result", steps=[changed_step])
    with pytest.raises(DeclarationError, match="未声明的上游接口"):
        Catalog([replace(module, provides={read: flow})])
    shared = replace(module, name="shared_probe", provides={})
    Catalog([module, shared])
    changed = replace(module, endpoints=(replace(read_endpoint, path="/new"), write_endpoint))
    assert digest_of([module]) != digest_of([changed])


# 原件按接口名回放；未覆盖明确失败，HTTP请求不泄漏专用回放头。
@pytest.mark.anyio
async def test_replay_endpoint_name(tmp_path: Path) -> None:
    (tmp_path / "receipt.json").write_text('{"accepted": true, "count": 1}')
    replay = Replay(
        upstream.name, [{"endpoint": read_endpoint.name, "file": "receipt.json"}], tmp_path
    )
    client = RemoteService(
        {upstream.name: RemoteConfig(base_url="https://replay.example")}, {upstream.name: replay}
    )
    try:
        gate = RemoteGate(client, (upstream,), [], "测试", endpoints=(read_endpoint,))
        reply = await gate.call(upstream, read_endpoint, Request(sku="x"))
        assert reply.data.count == 1 and replay.used[0]["endpoint"] == read_endpoint.name
        with pytest.raises(Exception, match="回放未覆盖"):
            await client.send(upstream, RemoteRequest("POST", "/read", effect="read"), [])
    finally:
        await client.close()
