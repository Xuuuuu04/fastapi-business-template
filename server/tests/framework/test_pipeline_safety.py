"""
流程安全边界：有限产出、未知结果、等待超时、阶段租约及组织查询。
"""

import time
from dataclasses import replace

import pytest
from sqlalchemy import update

from app.setup.build import Services
from shared.errors.framework import InvalidInput
from shared.errors.kinds import BusinessError, Kind
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.modules.catalog import Catalog
from shared.pipelines.recovery import resume
from shared.pipelines.tables import runs, stages
from shared.pipelines.views import detail, list_runs
from tests.framework.pipeline_sample import Ref, Store, module, pipeline
from tests.framework.test_pipelines import drain, piped, snapshot, start

pytestmark = pytest.mark.anyio
__all__ = ["piped"]


# 超大产出同时回滚本阶段数据，不登记下一个阶段。
async def test_large_output_rolls_back(piped: Services, monkeypatch) -> None:
    original = Store.record

    # 合成采集结果引用超过16KiB。
    async def large(self, name, reference):
        result = await original(self, name, reference)
        return Ref(reference="x" * 17000) if name == "collect" else result

    monkeypatch.setattr(Store, "record", large)
    run_id = await start(piped, "large")
    await drain(piped)
    root, rows, marks = await snapshot(piped, run_id)
    assert root["state"] == "failed" and marks == {"choose": 1}
    assert len(rows) == 2 and "collect" in rows[-1]["error"] and "16 KiB" in rows[-1]["error"]


# 外部效果未知必须停止推进，重试需要独立人工确认。
async def test_unknown_never_automatically_advances(piped: Services, monkeypatch) -> None:
    original = Store.record

    # 模拟调价已发出但结果无法确认，不访问外部系统。
    class Unknown(BusinessError):
        code = "sample_unknown"
        kind = Kind.UNKNOWN_RESULT
        message = "结果待确认"

    # 上游不确定的结果不允许自动重做。
    async def unknown(self, name, reference):
        if name == "collect":
            raise Unknown()
        return await original(self, name, reference)

    monkeypatch.setattr(Store, "record", unknown)
    run_id = await start(piped, "unknown")
    await drain(piped)
    assert (await snapshot(piped, run_id))[0]["state"] == "unknown"
    with pytest.raises(InvalidInput, match="外部结果待确认"):
        await resume(piped.database, piped.catalog, run_id)
    await drain(piped)
    assert (await snapshot(piped, run_id))[2] == {"choose": 1}


# 明确到达等待截止时间就失败，不能靠重试次数无限等待。
async def test_wait_timeout(piped: Services) -> None:
    run_id = await start(piped, "timeout")
    worker = Worker(piped.runtime, piped.queue, [], WorkerOptions())
    for _ in range(2):
        ticket = await piped.queue.claim(time.time())
        assert ticket is not None
        await worker.execute(ticket)
    async with piped.database.write() as connection:
        await connection.execute(
            update(stages).where(stages.c.name == "wait").values(wait_until=time.time() - 1)
        )
    await drain(piped)
    root, _, marks = await snapshot(piped, run_id)
    assert root["state"] == "failed" and "超时" in root["reason"]
    assert marks == {"choose": 1, "collect": 1}


# 旧尝试在新领取后不能改变流程、业务数据或下一阶段。
async def test_expired_stage_attempt_is_fenced(piped: Services) -> None:
    run_id = await start(piped, "lease")
    old = await piped.queue.claim(time.time())
    assert old is not None
    async with piped.database.write() as connection:
        await connection.execute(update(jobs).values(lease_until=time.time() - 1))
    await piped.queue.reclaim(time.time())
    new = await piped.queue.claim(time.time())
    assert new is not None and new.attempt == old.attempt + 1
    await Worker(piped.runtime, piped.queue, [], WorkerOptions()).execute(old)
    assert (await snapshot(piped, run_id))[2] == {}
    await Worker(piped.runtime, piped.queue, [], WorkerOptions()).execute(new)
    await drain(piped)
    assert (await snapshot(piped, run_id))[0]["state"] == "succeeded"


# 数据库按组织过滤，不把别的组织的流程摘要或细节透露给调用方。
async def test_views_are_org_scoped(piped: Services) -> None:
    run_id = await start(piped, "org")
    assert await list_runs(piped.database, org_id="org-b") == []
    assert await detail(piped.database, run_id, org_id="org-b") is None
    await drain(piped)
    found = await detail(piped.database, run_id, org_id="org-a")
    assert found is not None and len(found["stages"]) == 4
    assert "caller_json" not in found and "input_json" not in found
    assert all(item["run_url"] for item in found["stages"])


# 排队期间后续声明变化需暂停，接受格式后从首阶段自动运行。
async def test_queued_schema_change_requires_confirmation(piped: Services) -> None:
    queued = replace(pipeline, overlap="queue")
    changed_module = replace(
        module,
        pipelines=(queued,),
        schedules=(replace(module.schedules[0], contract=queued.start),),
    )
    piped.catalog = piped.queue.catalog = piped.runtime.catalog = Catalog([changed_module])
    piped.queue.pipelines.catalog = piped.catalog
    first = await start(piped, "before")
    second = await start(piped, "after")
    # 排队周期保存旧声明摘要，模拟当前周期完成前新部署改变后续格式。
    async with piped.database.write() as connection:
        await connection.execute(
            update(runs)
            .where(runs.c.id == second)
            .values(declarations_json='[{"name":"choose","signature":"old"}]')
        )
    await drain(piped)
    assert (await snapshot(piped, first))[0]["state"] == "succeeded"
    assert (await snapshot(piped, second))[0]["state"] == "version_blocked"
    await resume(piped.database, piped.catalog, second, accept_schema=True)
    await drain(piped)
    assert (await snapshot(piped, second))[0]["state"] == "succeeded"


# 直接公开操作也复用同一生成入口与运行记录，不依赖定时专用绕行。
async def test_public_start_runs_registered_flow(piped: Services) -> None:
    from shared.pipelines.plan import StartRequest
    from tests.framework.test_pipelines import CALLER

    data = pipeline.start.input(request=StartRequest[Ref](data=Ref(), cycle_key="public"))
    result = await piped.runtime.run(pipeline.start, data, caller=CALLER)
    await drain(piped)
    assert (await snapshot(piped, result.id))[0]["state"] == "succeeded"


# 同等待阶段跨组织最多一个检查在跑，忙时短事务重新排队。
async def test_wait_parallel_limit(piped: Services) -> None:
    from shared.pipelines.plan import StartRequest
    from shared.pipelines.runner import prepare
    from tests.framework.test_pipelines import CALLER

    first = await start(piped, "capacity")
    worker = Worker(piped.runtime, piped.queue, [], WorkerOptions())
    for _ in range(2):
        ticket = await piped.queue.claim(time.time())
        assert ticket is not None
        await worker.execute(ticket)
    first_ticket = await piped.queue.claim(time.time())
    assert first_ticket is not None
    context = await prepare(piped.queue, first_ticket)
    assert context is not None and context.allowed
    data = pipeline.start.input(request=StartRequest[Ref](data=Ref(), cycle_key="capacity"))
    other = await piped.runtime.submit(pipeline.start, data, caller=replace(CALLER, org_id="org-b"))
    for _ in range(2):
        ticket = await piped.queue.claim(time.time())
        assert ticket is not None
        await worker.execute(ticket)
    other_ticket = await piped.queue.claim(time.time())
    assert other_ticket is not None
    context = await prepare(piped.queue, other_ticket)
    assert context is not None and not context.allowed
    assert (await snapshot(piped, other))[0]["state"] == "waiting_external"
    assert (await snapshot(piped, first))[0]["state"] == "running"
    await worker.execute(first_ticket)
    await drain(piped)
