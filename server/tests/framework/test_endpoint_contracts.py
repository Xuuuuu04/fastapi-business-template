import json
from dataclasses import replace
from pathlib import Path

import httpx2
import pytest

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.errors.framework import DeclarationError, RemoteOutputInvalid, RemoteResultUnknown
from shared.graphs.observed import run_graph
from shared.graphs.static import flow_graph
from shared.model_calls.providers import FakeModel
from shared.modules.catalog import Catalog
from shared.public import Flow
from shared.records.models import RemoteCallRecord, run_from_dict
from shared.remote_calls.gate import RemoteGate
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.service import RemoteService
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


@pytest.mark.anyio
@pytest.mark.parametrize("operation", [read, write])
async def test_typed_call_and_graphs(tmp_path: Path, operation: object) -> None:
    seen: list[httpx2.Request] = []

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
    finally:
        await services.close()


def service(respond: object) -> RemoteService:
    return RemoteService(
        {upstream.name: RemoteConfig(base_url="https://protocol.example")},
        {upstream.name: httpx2.MockTransport(respond)},
        retry_waits=(0,),
    )


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


@pytest.mark.anyio
@pytest.mark.parametrize("status", [202, 408, 499, 503, 0])
async def test_write_unknown(status: int) -> None:
    attempts = 0

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


@pytest.mark.anyio
async def test_effect_overrides_method() -> None:
    calls = 0

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


def test_startup_checks_endpoints() -> None:
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


@pytest.mark.anyio
async def test_gate_passes_endpoint_name() -> None:
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.extensions.get("endpoint", ""))
        return httpx2.Response(200, json={"accepted": True, "count": 1})

    client = service(respond)
    try:
        gate = RemoteGate(client, (upstream,), [], "测试", endpoints=(read_endpoint,))
        reply = await gate.call(upstream, read_endpoint, Request(sku="x"))
        assert reply.data.count == 1 and seen == [read_endpoint.name]
    finally:
        await client.close()
