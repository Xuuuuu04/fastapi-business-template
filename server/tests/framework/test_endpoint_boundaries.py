"""
声明与兼容边界：存储调用、旧产品警告/严格模式、共享依赖和未知记录不被覆盖。
"""

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


# 存储协议仍由步骤声明，不让整个模块登记扩大当前步骤的权限。
class ReceiptStore:
    # 注入现有remote入口，存储不依赖具体传输实现。
    def __init__(self, remote: RemoteClient) -> None:
        self.remote = remote

    # 公开共享协议对象通过remote.call复用。
    async def read(self, input: Request) -> Receipt:
        return (await self.remote.call(upstream, read_endpoint, input)).data


# store路径也在计算图声明上游接口。
@step("读存储协议", reads=["sku"], writes=["result"], endpoints=[read_endpoint])
async def read_store(data: Work, store: ReceiptStore) -> None:
    data.result = await store.read(Request(sku=data.sku))


# 存储样例不在模板目录登记。
def store_module(declared: bool = True) -> object:
    part = read_store if declared else replace(read_store, endpoints=())
    return replace(
        module,
        store=ReceiptStore,
        provides={read: Flow("存储读", work=Work, result="result", steps=[part])},
    )


# SQLite/PostgreSQL均实际执行存储注入路径。
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


# 旧产品默认警告仍启动；严格开关使同一源码启动报错。
def test_legacy_warning_then_strict(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    with caplog.at_level(logging.WARNING, logger="server.remote_calls"):
        Catalog([price_module])
    assert "旧上游调用" in caplog.text
    with pytest.raises(DeclarationError, match="旧上游调用"):
        build(make_settings(tmp_path, remote_endpoints_strict=True), modules=[price_module])


# 动态旧路径在运行时也不能绕过严格开关；伪造名称不能改变写入效果。
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


# 同一协议曾有未知写入时，后来的409不能覆盖它，即使请求编号稳定。
@pytest.mark.anyio
async def test_unknown_before_refusal() -> None:
    calls = 0

    # 模拟首次超时、第二次拒绝；调用层必须保留第一次未知事实。
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


# 协议的来源模块进入依赖图，提供者源码变化会使消费方检查过期。
def test_shared_protocol_dependency() -> None:
    declaration = replace(read_endpoint)
    object.__setattr__(declaration, "source", "service.protocol_owner.store.contract")
    consumer = replace(module, endpoints=(declaration,))
    provider = replace(module, name="protocol_owner", provides={}, endpoints=(declaration,))
    consumer = replace(consumer, provides={})
    catalog = Catalog([consumer, provider])
    assert "protocol_owner" in catalog.links()[consumer.name]


# 动态选接口时仍能在启动发现完全没有声明，不必等请求触发才发现。
@step("动态选择接口", reads=["sku"], writes=["result"], remotes=[upstream])
async def read_dynamic(data: Work, remote: RemoteClient) -> None:
    chosen = read_endpoint
    data.result = (await remote.call(upstream, chosen, Request(sku=data.sku))).data


# 目标名称不能静态解析时明确未知，并指出缺少步骤声明。
def test_dynamic_call_without_declaration() -> None:
    dynamic = replace(
        module, provides={read: Flow("动态读", work=Work, result="result", steps=[read_dynamic])}
    )
    with pytest.raises(DeclarationError, match="未知（动态选择）"):
        Catalog([dynamic])


# 业务和上游共用Data时，生成文档只展开一次模型，避免重复维护和阅读。
def test_protocol_docs_share_models() -> None:
    from fastapi_docs.flow_doc import model_name, module_doc

    text = module_doc(Catalog([module]), module.name, {})
    assert "## 上游接口" in text and read_endpoint.name in text
    assert text.count(f"### {model_name(Request)}") == 1
    assert text.count(f"### {model_name(Receipt)}") == 1
    assert "### 上游数据" not in text


# 未接入Endpoint的旧模块不改变登记摘要格式，别名能力也照常保留。
def test_legacy_declaration_shape_is_unchanged() -> None:
    from shared.modules.digest import module_shape

    assert "endpoints" not in module_shape(price_module)
    assert "step_endpoints" not in module_shape(price_module)
