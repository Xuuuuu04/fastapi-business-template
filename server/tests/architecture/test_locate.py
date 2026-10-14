"""
独立业务词样例，不进入正式模块、路由或迁移。
"""

from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from fastapi import APIRouter, FastAPI
from fastapi_project.development.locate import locate
from fastapi_project.development.locate_routes import route_details

from shared.errors.framework import DeclarationError
from shared.modules.catalog import Catalog
from shared.public import Module, contract
from tests.framework.sample_modules import CalcInput, CalcResult, NoteStore, calc_flow

price = contract(
    "sample_price.adjust",
    "调整售价",
    input=CalcInput,
    output=CalcResult,
    access="public",
    aliases=("change price", "/api/v1/price/old"),
)
price_module = Module(
    "sample_price",
    "售价样例",
    "1",
    {price: calc_flow},
    store=NoteStore,
    aliases=("价格表", "price table"),
)
router = APIRouter(prefix="/api/v1/price")


# 端点引用与正式接口相同的公开约定。
@router.post("/adjust")
async def adjust_price() -> str:
    return price.name


# 中文、英文、现用路径、旧路径与规则编号均定位到真实声明。
@pytest.mark.parametrize(
    "query",
    ["价格表", "PRICE TABLE", "/api/v1/price/adjust", "/api/v1/price/old", "R-01", "规则标题"],
)
def test_business_queries(tmp_path: Path, query: str) -> None:
    folder = tmp_path / "doc/sample_price"
    folder.mkdir(parents=True)
    folder.joinpath("rules.md").write_text("## R-01 规则标题\n")
    flow = replace_flow_rule()
    catalog = Catalog([replace(price_module, provides={price: flow})])
    app = FastAPI()
    app.include_router(router)
    result = locate(catalog, tmp_path, query, routes=route_details(app))
    assert result["total"] == 1
    hit = result["results"][0]
    assert hit["operation"] == price.name
    assert hit["steps"]["items"][0]["source"].startswith("server/tests/")
    assert "uv run dev status --operation sample_price.adjust" in hit["next"]
    assert result["database_read"] is False


# 测试副本的规则不修改公用样例。
def replace_flow_rule():
    from shared.flow.flow import Flow

    return Flow(
        calc_flow.title,
        work=calc_flow.work,
        result=calc_flow.result,
        steps=[replace(s, rule="R-01") for s in calc_flow.steps],
    )


# 大项目1000操作，结果数量上限与省略数准确，检索本体一秒内。
def test_bounded_large_project(tmp_path: Path) -> None:
    operations = {
        contract(
            f"sample_price.op_{n}", "价格", input=CalcInput, output=CalcResult, access="public"
        ): calc_flow
        for n in range(1000)
    }
    catalog = Catalog([replace(price_module, provides=operations)])
    started = perf_counter()
    result = locate(catalog, tmp_path, "价格", limit=3)
    assert perf_counter() - started < 1
    assert len(result["results"]) == 3
    assert result["total"] == 1000 and result["omitted"] == 997


# 新别名冲突启动即发现；旧产品省略别名不增加约束。
@pytest.mark.parametrize("aliases", [(" ",), ("价格表", "价格表"), ("sample_price",)])
def test_invalid_module_aliases(aliases: tuple[str, ...]) -> None:
    with pytest.raises(DeclarationError):
        Catalog([replace(price_module, aliases=aliases)])


# 操作别名大小写冲突，以及失效操作引用都在启动发现。
def test_operation_conflict_and_missing_reference() -> None:
    other = replace(price, name="sample_price.other", aliases=("CHANGE PRICE",))
    with pytest.raises(DeclarationError, match="冲突"):
        Catalog([replace(price_module, provides={price: calc_flow, other: calc_flow})])
    flow = replace_flow_rule()
    flow.steps = (replace(flow.steps[0], uses=(other,)), *flow.steps[1:])
    with pytest.raises(DeclarationError, match="没有登记"):
        Catalog([replace(price_module, provides={price: flow})])


# meaning与表名定位，明细省略仍保留准确的下一步。
def test_fields_tables_and_detail_limit(tmp_path: Path) -> None:
    from sqlalchemy import MetaData, Table

    module = replace(
        price_module, tables=tuple(Table(f"sample_price_t{n}", MetaData()) for n in range(20))
    )
    catalog = Catalog([module])
    assert locate(catalog, tmp_path, "金额")["total"] == 1
    hit = locate(catalog, tmp_path, "sample_price_t19")["results"][0]
    assert len(hit["tables"]["items"]) == 12 and hit["tables"]["omitted"] == 8
    assert "未知" in hit["table_relation"]


# 新运行保存当时别名，旧JSON兼容且不猜历史别名。
@pytest.mark.anyio
async def test_aliases_in_real_run(sample) -> None:
    from decimal import Decimal

    from shared.access.caller import DEVELOPER
    from shared.graphs.observed import run_graph
    from shared.graphs.static import flow_graph
    from shared.records.models import run_from_dict
    from shared.records.stores import RunFilter
    from tests.framework.sample_modules import calc, calc_module

    aliased = replace(calc, aliases=("调价",))
    module = replace(calc_module, provides={aliased: calc_flow}, jobs=(), aliases=("价格表",))
    sample.runtime.catalog = Catalog([module])
    await sample.runtime.run(aliased, CalcInput(amount=Decimal("5")), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    assert run.aliases == ["调价"] and run.module_aliases == ["价格表"]
    assert "调价" in run_graph([run])
    assert "调价" in flow_graph(sample.runtime.catalog.binding(aliased))
    old = run.to_dict()
    del old["aliases"], old["module_aliases"]
    assert "未知（旧记录）" in run_graph([run_from_dict(old)])


# 定时计划和多阶段流程词回到已登记操作，不需要读取运行数据库。
def test_schedule_and_pipeline_names(tmp_path: Path) -> None:
    from datetime import timedelta
    from decimal import Decimal

    from shared.public import JobPlan, Pipeline, Schedule, Stage

    pipeline = Pipeline("sample_price.reprice", "整批售价", CalcInput, (Stage("adjust", price),))
    schedule = Schedule(
        "price_daily", "每日更新", price, CalcInput(amount=Decimal("5")), every=timedelta(days=1)
    )
    catalog = Catalog(
        [
            replace(
                price_module, jobs=(JobPlan(price),), schedules=(schedule,), pipelines=(pipeline,)
            )
        ]
    )
    assert locate(catalog, tmp_path, "price_daily")["results"][0]["operation"] == price.name
    hits = locate(catalog, tmp_path, "sample_price.reprice")["results"]
    assert {hit["operation"] for hit in hits} == {price.name, pipeline.start.name}


# 常规路由登记只读指定业务路由，动态写法回退，不猜测接口。
def test_registered_router_selection() -> None:
    import ast

    from fastapi_project.development.locate_routes import registered_routers

    from tests.framework.sample_routes import sample_router

    declaration = ast.parse('{"sample": (sample_routes.sample_router,)}').body[0].value
    assert registered_routers(
        declaration, {"sample_routes": ("tests.framework", "sample_routes")}
    ) == [sample_router]
    assert registered_routers(ast.parse("build_routers()").body[0].value, {}) is None
