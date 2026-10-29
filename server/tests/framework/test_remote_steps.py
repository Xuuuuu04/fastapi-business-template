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
    Endpoint,
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


class Sku(Data):
    sku: str = meaning("商品编号")


class Price(Data):
    price: int = meaning("合作方报价", unit="分")


class PriceQuery(Data):
    sku: str = meaning("商品编号")
    token: str = meaning("合作方口令", secret=True)


price_endpoint = Endpoint(
    "partner.price",
    "GET",
    "/prices/{sku}",
    input=PriceQuery,
    output=Price,
    effect="read",
    path_fields=("sku",),
)


class PriceWork(WorkData):
    sku: str = meaning("商品编号")
    price: int = meaning("合作方报价", unit="分")
    result: Price = meaning("操作结果")


class PriceStore:
    def __init__(self, remote: RemoteClient, cache: ModuleCache) -> None:
        self.remote, self.cache = remote, cache

    async def price(self, sku: str) -> int:
        cached = await self.cache.get_text(f"price:{sku}")
        if cached is not None:
            return int(cached)
        reply = await self.remote.call(partner, price_endpoint, PriceQuery(sku=sku, token="secret"))
        await self.cache.set_text(f"price:{sku}", str(reply.data.price), 60)
        return reply.data.price


ask_price = contract(
    "price_probe.ask", "询价", input=Sku, output=Price, access="public", effect="query"
)
cached_price = contract(
    "price_probe.cached", "缓存询价", input=Sku, output=Price, access="public", effect="query"
)


@step("询问合作方", reads=["sku"], writes=["price"], remotes=[partner], endpoints=[price_endpoint])
async def ask(data: PriceWork, remote: RemoteClient) -> None:
    reply = await remote.call(partner, price_endpoint, PriceQuery(sku=data.sku, token="secret"))
    data.price = reply.data.price


@step("读取价格", reads=["sku"], writes=["price"], endpoints=[price_endpoint])
async def read_price(data: PriceWork, store: PriceStore) -> None:
    data.price = await store.price(data.sku)


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
    endpoints=(price_endpoint,),
    kind="capability",
)


async def services_with(tmp_path: Path, seen: list[str]) -> Services:
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
            ("partner", "/prices/{sku}", 200)
        ]
        assert "secret" not in str(record.to_dict())
    finally:
        await services.close()


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


def test_remote_declarations_are_checked() -> None:
    other = remote("other", "未登记系统")
    save = contract(
        "remote_order.save",
        "保存后询价",
        input=Sku,
        output=Price,
        access="public",
        effect="command",
    )

    @step("询问未登记系统", reads=["sku"], writes=["price"], remotes=[other])
    async def ask_other(data: PriceWork, remote: RemoteClient) -> None:
        data.price = 0

    @step("先保存", reads=["sku"], saves=True)
    async def save_first(data: PriceWork, store: NoteStore) -> None:
        await store.add(data.sku)

    flow = Flow(
        "保存后询价", work=PriceWork, result="result", steps=[save_first, ask_other, finish]
    )
    module = Module(
        "remote_order",
        "顺序测试",
        "1",
        {save: flow},
        store=NoteStore,
        remotes=(partner,),
        kind="capability",
    )
    with pytest.raises(DeclarationError) as caught:
        Catalog([module])
    problems = caught.value.problems
    assert any("没有在模块声明的 remotes 中登记" in item for item in problems)
    assert any("写入事务开始" in item and "之后调用外部服务" in item for item in problems)
