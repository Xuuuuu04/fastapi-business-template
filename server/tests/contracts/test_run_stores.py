"""
运行记录保存位置的约定测试：内存实现和数据库实现对同一组操作给出相同结果。
以后新增保存位置（例如专门的排查数据库）时，把它加进 STORES 即可复用全部检查。
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from shared.db.database import Database
from shared.records.models import RunRecord, StepRecord
from shared.records.stores import MemoryRunStore, RunFilter, RunStore, SqlRunStore
from tests.testing_app import database_url, reset_database

pytestmark = pytest.mark.anyio

STORES = ["memory", "database"]


# 按名称创建一个保存位置。
@pytest.fixture(params=STORES)
async def store(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[RunStore]:
    if request.param == "memory":
        yield MemoryRunStore(100)
        return
    url = database_url(tmp_path)
    await reset_database(url)
    database = Database(url)
    yield SqlRunStore(database)
    await database.close()


# 生成一条运行记录。
def make_run(
    run_id: str, root: str, started: float, status: str = "ok", module: str = "m"
) -> RunRecord:
    run = RunRecord(
        run_id,
        root,
        "" if run_id == root else root,
        "",
        f"{module}.op",
        "操作",
        module,
        "1",
        "dev",
        "q",
        "",
        "x",
        started,
    )
    run.status = status
    run.steps = [
        StepRecord(
            "s1", "count", "计算", "compute", "R-01", "a.py:1", status="ok", values=["合计：3 项"]
        )
    ]
    return run


# 保存后能按编号完整读回，包括步骤详情。
async def test_save_and_get(store: RunStore) -> None:
    await store.save([make_run("a", "a", 1.0)])
    found = await store.get("a")
    assert found is not None and found.steps[0].values == ["合计：3 项"]
    assert await store.get("missing") is None


# 按最外层编号读回整棵调用树。
async def test_tree(store: RunStore) -> None:
    await store.save([make_run("a", "a", 1.0), make_run("b", "a", 2.0), make_run("c", "c", 3.0)])
    assert sorted(run.id for run in await store.tree("a")) == ["a", "b"]


# 按条件查询最近的最外层运行，最新的在前。
async def test_recent_filters(store: RunStore) -> None:
    runs = [
        make_run("a", "a", 1.0),
        make_run("b", "b", 2.0, "failed"),
        make_run("c", "c", 3.0, module="n"),
    ]
    await store.save([*runs, make_run("d", "a", 4.0)])
    assert [run.id for run in await store.recent(RunFilter(), 10)] == ["c", "b", "a"]
    assert [run.id for run in await store.recent(RunFilter(status="failed"), 10)] == ["b"]
    assert [run.id for run in await store.recent(RunFilter(module="n"), 10)] == ["c"]
    assert [run.id for run in await store.recent(RunFilter(before=3.0), 1)] == ["b"]


# 清理早于指定时间的记录。
async def test_clean(store: RunStore) -> None:
    await store.save([make_run("a", "a", 1.0), make_run("b", "b", 5.0)])
    assert await store.clean(3.0) == 1
    assert await store.get("a") is None and await store.get("b") is not None
