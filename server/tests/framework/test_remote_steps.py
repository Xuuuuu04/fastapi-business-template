"""
通过执行器验证 remote 和 cache 的注入：步骤参数和存储构造参数都能拿到，
调用写进运行记录；未声明的外部系统和写入事务之后的外部调用在启动时被拒绝。
"""

from pathlib import Path

import httpx2
import pytest

from app.setup.build import Services, build
from shared.access.caller import SYSTEM
from shared.errors.framework import DeclarationError
from shared.graphs.observed import run_graph
from shared.model_calls.providers import FakeModel
from shared.modules.catalog import Catalog
from shared.public import (
    Data,
    Flow,
    Module,
    ModuleCache,
    RemoteClient,
    WorkData,
    contract,
    meaning,
    remote,
    step,
)
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.service import RemoteService
from tests.framework.sample_modules import NoteStore
from tests.testing_app import make_settings, reset_database

partner = remote("partner", "合作方")


# 外部接口测试输入的商品编号。
class Sku(Data):
    sku: str = meaning("商品编号")


# 外部接口测试返回的价格，单位为分。
class Price(Data):
    price: int = meaning("合作方报价", unit="分")


# 外部接口测试各步骤共享的编号、价格和结果。
class PriceWork(WorkData):
    sku: str = meaning("商品编号")
    price: int = meaning("合作方报价", unit="分")
    result: Price = meaning("操作结果")


# 外部接口测试的数据访问实现，同时使用外部请求与缓存。
class PriceStore:
    # 构造参数名 remote 和 cache 决定框架注入外部接口和缓存。
    def __init__(self, remote: RemoteClient, cache: ModuleCache) -> None:
        self.remote, self.cache = remote, cache

    # 先查缓存，没有时询问合作方并缓存一分钟。
    async def price(self, sku: str) -> int:
        cached = await self.cache.get_text(f"price:{sku}")
        if cached is not None:
            return int(cached)
        reply = await self.remote.get(partner, f"/prices/{sku}")
        await self.cache.set_text(f"price:{sku}", str(reply.data["price"]), 60)
        return int(reply.data["price"])


ask_price = contract("price_probe.ask", "询价", input=Sku, output=Price, access="public")
cached_price = contract("price_probe.cached", "缓存询价", input=Sku, output=Price, access="public")


# 步骤直接通过 remote 参数询价。
@step("询问合作方", reads=["sku"], writes=["price"], remotes=[partner])
async def ask(data: PriceWork, remote: RemoteClient) -> None:
    reply = await remote.get(partner, f"/prices/{data.sku}", params={"token": "secret"})
    data.price = int(reply.data["price"])


# 通过存储实现询价，存储实现自己决定是否使用缓存。
@step("读取价格", reads=["sku"], writes=["price"])
async def read_price(data: PriceWork, store: PriceStore) -> None:
    data.price = await store.price(data.sku)


# 把价格整理成结果。
@step("整理结果", reads=["price"], writes=["result"])
def finish(data: PriceWork) -> None:
    data.result = Price(price=data.price)


price_module = Module(
    "price_probe",
    "询价测试",
    "1",
    {
        ask_price: Flow("询价", work=PriceWork, result="result", steps=[ask, finish]),
        cached_price: Flow("缓存询价", work=PriceWork, result="result", steps=[read_price, finish]),
    },
    store=PriceStore,
    remotes=(partner,),
)


# 组装只含询价模块的服务，并把合作方替换成计数的模拟接口。
async def services_with(tmp_path: Path, seen: list[str]) -> Services:
    # 按路径返回固定报价，并记下收到的请求路径。
    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        graph = run_graph(list(services.recorder.active.values()))
        calls = [line for line in graph.splitlines() if "_external" in line and '["' in line]
        assert calls and all(line.endswith(":::running") for line in calls)
        return httpx2.Response(200, json={"price": 1200})

    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    services = build(settings, modules=[price_module], provider=FakeModel())
    configs = {"partner": RemoteConfig(base_url="https://partner.example")}
    services.runtime.remotes = RemoteService(configs, {"partner": httpx2.MockTransport(respond)})
    return services


# 步骤的 remote 参数发出请求，运行记录保存调用概要但不保存查询参数。
@pytest.mark.anyio
async def test_remote_step_is_recorded(tmp_path: Path) -> None:
    seen: list[str] = []
    services = await services_with(tmp_path, seen)
    run_ids: list[str] = []
    try:
        result = await services.runtime.run(
            ask_price, Sku(sku="a1"), caller=SYSTEM, on_start=run_ids.append
        )
        assert result.price == 1200 and seen == ["/prices/a1"]
        record = await services.recorder.get(run_ids[0])
        assert record is not None
        first = record.steps[0]
        assert first.kind == "remote"
        assert [(item.remote, item.path, item.status) for item in first.remotes] == [
            ("partner", "/prices/a1", 200)
        ]
        assert "secret" not in str(record.to_dict())
    finally:
        await services.close()


# 存储实现按构造参数名拿到 remote 和 cache；第二次读取命中缓存，不再请求合作方。
@pytest.mark.anyio
async def test_store_gets_remote_and_cache(tmp_path: Path) -> None:
    seen: list[str] = []
    services = await services_with(tmp_path, seen)
    run_ids: list[str] = []
    try:
        for _ in range(2):
            found = await services.runtime.run(
                cached_price, Sku(sku="b2"), caller=SYSTEM, on_start=run_ids.append
            )
            assert found.price == 1200
        assert seen == ["/prices/b2"]
        first, second = [await services.recorder.get(run_id) for run_id in run_ids]
        assert first is not None and second is not None
        assert (first.steps[0].cache_misses, first.steps[0].cache_hits) == (1, 0)
        assert (second.steps[0].cache_misses, second.steps[0].cache_hits) == (0, 1)
    finally:
        await services.close()


# 步骤使用未在模块登记的外部系统，或在保存步骤之后调用外部系统，启动检查都会报出。
def test_remote_declarations_are_checked() -> None:
    other = remote("other", "未登记系统")
    save = contract("remote_order.save", "保存后询价", input=Sku, output=Price, access="public")

    # 声明了未登记的外部系统。
    @step("询问未登记系统", reads=["sku"], writes=["price"], remotes=[other])
    async def ask_other(data: PriceWork, remote: RemoteClient) -> None:
        data.price = 0

    # 先写入数据库。
    @step("先保存", reads=["sku"], saves=True)
    async def save_first(data: PriceWork, store: NoteStore) -> None:
        await store.add(data.sku)

    flow = Flow(
        "保存后询价", work=PriceWork, result="result", steps=[save_first, ask_other, finish]
    )
    module = Module(
        "remote_order", "顺序测试", "1", {save: flow}, store=NoteStore, remotes=(partner,)
    )
    with pytest.raises(DeclarationError) as caught:
        Catalog([module])
    problems = caught.value.problems
    assert any("没有在模块声明的 remotes 中登记" in item for item in problems)
    assert any("写入事务开始" in item and "之后调用外部服务" in item for item in problems)
