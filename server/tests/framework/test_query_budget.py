import pytest
from sqlalchemy import insert

from app.setup.build import Services, build
from shared.access.caller import ANONYMOUS
from shared.config.settings import Settings
from shared.db.budget import QueryBudget, QueryPolicy
from shared.errors.framework import DeclarationError, StepRuleBroken
from shared.graphs.observed import run_graph, run_report
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from shared.records.evidence import run_evidence
from shared.records.models import run_from_dict
from shared.records.stores import RunFilter
from tests.framework.query_budget_sample import (
    SAMPLE_BUDGET,
    Input,
    items,
    module_for,
    sample_metadata,
)
from tests.testing_app import prepare_test_database


async def sample(settings: Settings, budget: QueryBudget | None = SAMPLE_BUDGET) -> Services:
    await prepare_test_database(settings.database_url)
    built = build(settings, modules=[module_for(budget)])
    async with built.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
        await connection.execute(insert(items), [dict(id=i, name="商品") for i in range(250)])
    return built


async def close_sample(built: Services) -> None:
    try:
        async with built.database.write() as connection:
            await connection.run_sync(sample_metadata.drop_all)
    finally:
        await built.close()


@pytest.mark.anyio
async def test_loop_fails_batch_passes(settings: Settings) -> None:
    built = await sample(settings)
    item = next(iter(built.catalog.bindings))
    try:
        with pytest.raises(StepRuleBroken, match="循环里逐行查询"):
            await built.runtime.run(item, Input(), caller=ANONYMOUS)
        failed = (await built.recorder.recent(RunFilter(top_only=False), 10))[0]
        assert failed.status == "failed"
        assert failed.query_budget["actual"]["queries"] == 25
        assert "Store.find_one" in failed.query_budget["repeated"][0]["source"]
        assert "Store.find_one" in run_graph([failed])
        assert "超额" in run_report([failed], failed.id)
        result = await built.runtime.run(item, Input(batch=True), caller=ANONYMOUS)
        assert result.rows == 25
        good = (await built.recorder.recent(RunFilter(top_only=False), 10))[0]
        assert good.query_budget["actual"] == dict(queries=1, rows=25, bytes=190)
        assert run_from_dict(good.to_dict()).query_budget == good.query_budget
        assert run_evidence(good)["query_budget"] == good.query_budget
        assert "查询额度" in flow_graph(built.catalog.binding(item))
    finally:
        await close_sample(built)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "declared,env", [(False, "production"), (True, "production"), (True, "local")]
)
async def test_only_test_environment_fails(settings: Settings, declared: bool, env: str) -> None:
    built = await sample(settings, QueryBudget(queries=2) if declared else None)
    built.runtime.query_policy = QueryPolicy(env)
    item = next(iter(built.catalog.bindings))
    try:
        await built.runtime.run(item, Input(size=220), caller=ANONYMOUS)
        run = (await built.recorder.recent(RunFilter(top_only=False), 10))[0]
        assert run.status == "ok"
        assert run.query_budget["actual"]["queries"] == 220
        assert run.query_budget["actual"]["rows"] == 220
        assert len(run.steps[0].database) == 200
        assert run.query_budget["repeated"]
    finally:
        await close_sample(built)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "budget,key", [(QueryBudget(rows=2), "rows"), (QueryBudget(bytes=2), "bytes")]
)
async def test_rows_and_bytes(settings: Settings, budget: QueryBudget, key: str) -> None:
    built = await sample(settings, budget)
    try:
        with pytest.raises(StepRuleBroken):
            await built.runtime.run(
                next(iter(built.catalog.bindings)), Input(batch=True), caller=ANONYMOUS
            )
        assert (
            key
            in (await built.recorder.recent(RunFilter(top_only=False), 10))[0].query_budget[
                "exceeded"
            ]
        )
    finally:
        await close_sample(built)


def test_invalid_declaration() -> None:
    with pytest.raises(DeclarationError, match="queries 必须是正整数"):
        Catalog([module_for(QueryBudget(queries=-1))])


@pytest.mark.anyio
async def test_default_budget_fails_in_test(settings: Settings) -> None:
    built = await sample(settings, None)
    built.runtime.query_policy = QueryPolicy("test")
    try:
        with pytest.raises(StepRuleBroken, match="逐行查询"):
            await built.runtime.run(
                next(iter(built.catalog.bindings)), Input(size=120), caller=ANONYMOUS
            )
    finally:
        await close_sample(built)


@pytest.mark.anyio
@pytest.mark.postgres_only
async def test_postgres_explain(settings: Settings) -> None:
    built = await sample(settings, QueryBudget(rows=2))
    built.runtime.query_policy = QueryPolicy("test", True)
    try:
        with pytest.raises(StepRuleBroken):
            await built.runtime.run(
                next(iter(built.catalog.bindings)), Input(batch=True), caller=ANONYMOUS
            )
        run = (await built.recorder.recent(RunFilter(top_only=False), 10))[0]
        call = run.steps[0].database[0]
        assert call.explain_status == "ok" and call.explain
        assert set(call.explain[0]) <= {
            "Node Type",
            "Relation Name",
            "Plan Rows",
            "Plan Width",
            "Total Cost",
        }
        assert not QueryPolicy("production", True).explain_enabled()
    finally:
        await close_sample(built)


@pytest.mark.anyio
async def test_budget_failure_rolls_back(settings: Settings) -> None:
    from sqlalchemy import select

    from shared.public import Flow, Module
    from tests.framework.query_budget_sample import SavingStore, Work, load_items, save_item

    built = await sample(settings)
    item = next(iter(built.catalog.bindings))
    flow = Flow("回滚", work=Work, result="result", steps=[save_item, load_items])
    built.runtime.catalog = Catalog(
        [
            Module(
                "query_sample",
                "回滚",
                "1",
                provides={item: flow},
                store=SavingStore,
                tables=(items,),
                kind="capability",
            )
        ]
    )
    try:
        with pytest.raises(StepRuleBroken):
            await built.runtime.run(item, Input(), caller=ANONYMOUS)
        async with built.database.read() as connection:
            assert await connection.scalar(select(items.c.id).where(items.c.id == 999)) is None
        run = (await built.recorder.recent(RunFilter(top_only=False), 10))[0]
        assert run.writes == "rolled_back"
    finally:
        await close_sample(built)


@pytest.mark.anyio
async def test_nested_operation_budget(settings: Settings) -> None:
    from shared.public import Call, Flow, contract, step
    from tests.framework.query_budget_sample import Output, Work

    built = await sample(settings)
    child = next(iter(built.catalog.bindings))

    @step("调用两次", reads=["size", "batch"], writes=["result"], uses=[child])
    async def load_twice(data: Work, call: Call) -> None:
        input = Input(size=data.size, batch=data.batch)
        await call(child, input)
        data.result = await call(child, input)

    outer = contract(
        "query_sample.outer",
        "上层额度",
        input=Input,
        output=Output,
        access="public",
        query_budget=QueryBudget(queries=1),
        aliases=("上层查询",),
        effect="command",
    )
    from dataclasses import replace

    module = built.catalog.modules["query_sample"]
    provides = {
        **module.provides,
        outer: Flow("调用", work=Work, result="result", steps=[load_twice]),
    }
    built.runtime.catalog = Catalog([replace(module, provides=provides, aliases=("查询模块",))])
    try:
        with pytest.raises(StepRuleBroken):
            await built.runtime.run(outer, Input(size=1, batch=True), caller=ANONYMOUS)
        records = await built.recorder.recent(RunFilter(top_only=False), 10)
        run = next(record for record in records if record.contract == outer.name)
        assert run.query_budget["actual"]["queries"] == 2
        assert run.query_budget["actual"]["rows"] == 2
        assert len(run.query_children["locations"]) == 1
        assert run.aliases == ["上层查询"] and run.module_aliases == ["查询模块"]
    finally:
        await close_sample(built)


@pytest.mark.anyio
@pytest.mark.postgres_only
async def test_explain_uses_operation_total(settings: Settings) -> None:
    from dataclasses import replace

    from shared.public import Flow, step
    from tests.framework.query_budget_sample import Store, Work, load_items

    built = await sample(settings, QueryBudget(queries=5))
    built.runtime.query_policy = QueryPolicy("test", True)
    item = next(iter(built.catalog.bindings))

    @step("先读取", reads=["size"])
    async def load_first(data: Work, store: Store) -> None:
        for identity in range(data.size):
            await store.find_one(identity)

    module = built.catalog.modules["query_sample"]
    flow = Flow("分步查询", work=Work, result="result", steps=[load_first, load_items])
    built.runtime.catalog = Catalog([replace(module, provides={item: flow})])
    try:
        with pytest.raises(StepRuleBroken):
            await built.runtime.run(item, Input(size=3), caller=ANONYMOUS)
        run = (await built.recorder.recent(RunFilter(top_only=False), 10))[0]
        assert run.query_budget["actual"]["queries"] == 6
        assert run.steps[1].database[-1].explain_status == "ok"
        assert run.steps[1].database[-1].explain
    finally:
        await close_sample(built)
