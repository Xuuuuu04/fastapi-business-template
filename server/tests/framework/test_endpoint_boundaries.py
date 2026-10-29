import logging
from dataclasses import replace
from pathlib import Path

import httpx2
import pytest

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.errors.framework import DeclarationError, RemoteResultUnknown, StepRuleBroken
from shared.model_calls.providers import FakeModel
from shared.modules.catalog import Catalog
from shared.public import Flow, RemoteClient, step
from shared.records.models import RemoteCallRecord
from shared.remote_calls.gate import RemoteGate
from shared.remote_calls.service import RemoteRequest
from tests.framework.endpoint_sample import (
    Receipt,
    Request,
    Work,
    module,
    read,
    read_endpoint,
    upstream,
    write_endpoint,
)
from tests.framework.test_endpoint_contracts import service
from tests.framework.test_remote_steps import price_module
from tests.testing_app import make_settings, reset_database


class ReceiptStore:
    def __init__(self, remote: RemoteClient) -> None:
        self.remote = remote

    async def read(self, input: Request) -> Receipt:
        return (await self.remote.call(upstream, read_endpoint, input)).data


@step("读存储协议", reads=["sku"], writes=["result"], endpoints=[read_endpoint])
async def read_store(data: Work, store: ReceiptStore) -> None:
    data.result = await store.read(Request(sku=data.sku))


def store_module(declared: bool = True) -> object:
    part = read_store if declared else replace(read_store, endpoints=())
    return replace(
        module,
        store=ReceiptStore,
        provides={read: Flow("存储读", work=Work, result="result", steps=[part])},
    )


@pytest.mark.anyio
async def test_store_protocol(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    services = build(settings, modules=[store_module()], provider=FakeModel())
    services.runtime.remotes = service(
        lambda request: httpx2.Response(200, json={"accepted": True, "count": 3})
    )
    try:
        reply = await services.runtime.run(read, Request(sku="x"), caller=SYSTEM)
        assert reply.count == 3
    finally:
        await services.close()
    with pytest.raises(DeclarationError, match="未声明的上游接口"):
        Catalog([store_module(False)])


def test_legacy_warning_then_strict(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    with caplog.at_level(logging.WARNING, logger="server.remote_calls"):
        Catalog([price_module])
    assert "旧上游调用" in caplog.text
    with pytest.raises(DeclarationError, match="旧上游调用"):
        build(make_settings(tmp_path, remote_endpoints_strict=True), modules=[price_module])


@pytest.mark.anyio
async def test_runtime_strict_and_forgery() -> None:
    client = service(lambda request: httpx2.Response(200, json={"accepted": True, "count": 1}))
    client.strict_endpoints = True
    gate = RemoteGate(client, (upstream,), [], "测试", endpoints=(write_endpoint,))
    try:
        with pytest.raises(StepRuleBroken, match="严格接口模式"):
            await gate.get(upstream, "/read")
        with pytest.raises(StepRuleBroken, match="声明不一致"):
            await gate.send(
                upstream,
                RemoteRequest("POST", "/write", endpoint=write_endpoint.name, effect="read"),
            )
        with pytest.raises(StepRuleBroken, match="未声明"):
            await gate.call(upstream, read_endpoint, Request(sku="x"))
    finally:
        await client.close()


@pytest.mark.anyio
async def test_unknown_before_refusal() -> None:
    calls = 0

    def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx2.ReadTimeout("timeout", request=request)
        return httpx2.Response(409, json={"accepted": False, "count": 0})

    client = service(respond)
    records: list[RemoteCallRecord] = []
    gate = RemoteGate(client, (upstream,), records, "测试", endpoints=(write_endpoint,))
    try:
        with pytest.raises(RemoteResultUnknown):
            await gate.call(upstream, write_endpoint, Request(sku="x"), key="stable")
        assert calls == 2 and records[0].outcome == "unknown"
    finally:
        await client.close()


def test_shared_protocol_dependency() -> None:
    declaration = replace(read_endpoint)
    object.__setattr__(declaration, "source", "service.protocol_owner.store.contract")
    consumer = replace(module, endpoints=(declaration,))
    provider = replace(module, name="protocol_owner", provides={}, endpoints=(declaration,))
    consumer = replace(consumer, provides={})
    catalog = Catalog([consumer, provider])
    assert "protocol_owner" in catalog.links()[consumer.name]


@step("动态选择接口", reads=["sku"], writes=["result"], remotes=[upstream])
async def read_dynamic(data: Work, remote: RemoteClient) -> None:
    chosen = read_endpoint
    data.result = (await remote.call(upstream, chosen, Request(sku=data.sku))).data


def test_dynamic_call_without_declaration() -> None:
    dynamic = replace(
        module, provides={read: Flow("动态读", work=Work, result="result", steps=[read_dynamic])}
    )
    with pytest.raises(DeclarationError, match="未知（动态选择）"):
        Catalog([dynamic])
