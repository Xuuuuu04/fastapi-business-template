"""
查询额度的未知状态、历史读取、子操作累计及演练/项目输出。
"""

from typing import Any

import pytest
from fastapi_project.development.query_budget import latest_query, query_status
from sqlalchemy import literal, select

from shared.db.access import Db
from shared.db.budget import QueryBudget, comparison, merge_child
from shared.db.database import Database
from shared.db.sizing import value_bytes
from shared.modules.catalog import Catalog
from shared.records.evidence import run_evidence
from shared.records.models import RunRecord, StepRecord
from tests.framework.query_budget_sample import module_for


# 最小记录只包含框架字段，不添加预置业务。
def record() -> RunRecord:
    return RunRecord(
        "r",
        "r",
        "",
        "",
        "query_sample.read",
        "测试",
        "query_sample",
        "1",
        "dev",
        "",
        "",
        "anonymous",
        1,
    )


# scalar的结果值已测大小，但原查询返回行数仍未知，不等同于count聚合值。
@pytest.mark.anyio
async def test_unknown_scalar(tmp_path: Any) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/unknown.db")
    run = record()
    step = StepRecord("s", "load", "读取", "read", "", "test.py:1")
    run.steps.append(step)
    try:
        async with database.read() as connection:
            db = Db(connection, read_only=True, place="测试", record=step)
            assert await db.scalar(select(literal(100000))) == 100000
        measured = comparison(run, QueryBudget(rows=5), True)
        assert measured["unknown"]["rows"] == 1
        assert measured["actual"]["rows"] == 0
        assert measured["actual"]["bytes"] == 6
        assert not measured["exceeded"]
        assert value_bytes({"body": ["x" * 65000]}) == 65004
        assert value_bytes(object()) is None
        assert value_bytes("商品🥺") == 10
    finally:
        await database.close()


# 上层预算不能靠多次调用子操作绕过；每个位置仍记录真实次数。
def test_child_totals_and_latest_failed() -> None:
    run = record()
    child = record()
    step = StepRecord(
        "s",
        "load",
        "读取",
        "read",
        "",
        "test.py:1",
        database_count=11,
        database_rows=11,
        database_bytes=100,
        database_functions={"store.py · find": dict(queries=11, rows=11, bytes=100)},
    )
    child.steps = [step]
    child.query_budget = comparison(child, QueryBudget(), True)
    merge_child(run, child)
    merge_child(run, child)
    result = comparison(run, QueryBudget(queries=20, repeated=20), True)
    assert result["actual"]["queries"] == 22
    assert result["repeated"][0]["queries"] == 22
    run.query_budget, run.status = result, "failed"
    cases = [dict(outcome="failed", current=True, runs=[run_evidence(run)])]
    module = module_for()
    binding = Catalog([module]).by_name["query_sample.read"]
    view = query_status(binding, cases, "query_sample.read")
    assert view["query_actual"]["measured"] == result
    assert view["query_actual"]["outcome"] == "failed"
    assert latest_query([], "query_sample.read") == dict(measured="未知")
    assert view["query_budget"]["queries"] == 20


# 老测试证据可以没有运行号/时刻，新增视图必须给未知而不是抛异常。
def test_old_query_evidence_is_unknown() -> None:
    cases = [dict(outcome="passed", runs=[dict(operation="query_sample.read", steps=[])])]
    view = latest_query(cases, "query_sample.read")
    assert view["run_id"] == "未知" and view["started_at"] == "未知"
    assert view["measured"] == "未知" and view["status"] == "未知"


# 保留主干2.11.0公开约定中别名的原位置，新增额度仍是可选字段。
def test_alias_contract_position_is_compatible() -> None:
    from shared.modules.contract import Contract
    from tests.framework.query_budget_sample import Input, Output

    item = Contract(
        "query_sample.read",
        "查询",
        Input,
        Output,
        "public",
        (),
        True,
        30,
        False,
        False,
        ("读取商品",),
    )
    assert item.aliases == ("读取商品",) and item.query_budget is None
