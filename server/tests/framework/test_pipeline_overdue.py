"""
最晚完成时间与通知队列：默认逾期继续，显式暂停可恢复，未知结果不被逾期覆盖。
"""

from dataclasses import replace
from datetime import UTC, datetime
from datetime import time as daily_time

import pytest
from sqlalchemy import func, select

from app.setup.build import Services
from shared.modules.catalog import Catalog
from shared.pipelines.overdue import check, deadline
from shared.pipelines.plan import DailyTime, StartRequest
from shared.pipelines.recovery import resume
from shared.pipelines.tables import notifications, runs
from tests.framework.pipeline_sample import Ref, module, pipeline
from tests.framework.test_fanout import fanout
from tests.framework.test_pipelines import CALLER, drain, piped, snapshot

pytestmark = pytest.mark.anyio
__all__ = ["piped", "fanout"]


# 共用四阶段模块和夹具，仅新增明确的截止声明。
async def start_due(services: Services, policy: str = "continue") -> str:
    changed = replace(pipeline, complete_by=DailyTime(daily_time(9, 30)), on_overdue=policy)
    owner = replace(
        module,
        pipelines=(changed,),
        schedules=(replace(module.schedules[0], contract=changed.start),),
    )
    services.catalog = services.queue.catalog = services.runtime.catalog = Catalog([owner])
    services.queue.pipelines.catalog = services.catalog
    request = StartRequest[Ref](
        data=Ref(), cycle_key="due", period=datetime(2020, 1, 1, tzinfo=UTC)
    )
    return await services.runtime.submit(
        changed.start, changed.start.input(request=request), caller=CALLER
    )


# 默认逾期继续产出，重复检查只登记一个pending通知，不能说已经提醒。
async def test_overdue_continues_and_enqueues_once(piped: Services) -> None:
    run_id = await start_due(piped)
    await check(piped.queue, datetime(2020, 1, 2, tzinfo=UTC).timestamp())
    await check(piped.queue, datetime(2020, 1, 3, tzinfo=UTC).timestamp())
    root, _, _ = await snapshot(piped, run_id)
    assert root["overdue"] is True and root["state"] == "running"
    async with piped.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(notifications)) == 1
        assert await connection.scalar(select(notifications.c.state)) == "pending"
    await drain(piped)
    root, _, _ = await snapshot(piped, run_id)
    assert root["state"] == "succeeded" and root["overdue"] is True


# pause阻止首个尚未开始的阶段，人工继续不会重新选来源或抹去逾期事实。
async def test_overdue_pause_and_resume(piped: Services) -> None:
    run_id = await start_due(piped, "pause")
    await check(piped.queue, datetime(2020, 1, 2, tzinfo=UTC).timestamp())
    await drain(piped)
    root, _, marks = await snapshot(piped, run_id)
    assert root["state"] == "overdue_paused" and marks == {}
    await resume(piped.database, piped.catalog, run_id)
    await drain(piped)
    root, _, marks = await snapshot(piped, run_id)
    assert root["state"] == "succeeded" and root["overdue"] is True
    assert marks["choose"] == 1


# 夜间周期明确跨日，截止日期不从字符串周期键猜，也不会因后续声明改变而漂移。
def test_deadline_is_explicit_local_cycle_time() -> None:
    changed = replace(pipeline, complete_by=DailyTime(daily_time(9, 30), days_after=1))
    request = StartRequest[Ref](data=Ref(), period=datetime(2020, 1, 1, 14, tzinfo=UTC))
    assert deadline(changed, request, 0) == datetime(2020, 1, 2, 1, 30, tzinfo=UTC).timestamp()


# 逾期发生在阶段执行中，本阶段业务照常提交，再停在下一阶段。
async def test_pause_after_inflight_stage_commits(piped: Services, monkeypatch) -> None:
    import time

    from shared.jobs.worker import Worker, WorkerOptions
    from tests.framework.pipeline_sample import Store

    original = Store.record
    run_id = await start_due(piped, "pause")

    # 模拟截止时间恰好在业务计算期间到达，不用固定sleep安排先后顺序。
    async def due_during(self, name, reference):
        if name == "choose":
            await check(piped.queue, datetime(2020, 1, 2, tzinfo=UTC).timestamp())
        return await original(self, name, reference)

    monkeypatch.setattr(Store, "record", due_during)
    ticket = await piped.queue.claim(time.time())
    assert ticket is not None
    await Worker(piped.runtime, piped.queue, [], WorkerOptions()).execute(ticket)
    root, rows, marks = await snapshot(piped, run_id)
    assert root["state"] == "overdue_paused" and rows[0]["state"] == "succeeded"
    assert marks == {"choose": 1} and root["current_stage"] == "collect"
    await drain(piped)
    monkeypatch.setattr(Store, "record", original)
    await resume(piped.database, piped.catalog, run_id)
    await drain(piped)
    assert (await snapshot(piped, run_id))[2]["choose"] == 1


# 分段任务在已提交5000行之后暂停，继续时从原游标处理剩余数据。
async def test_segmented_member_pauses_at_batch_boundary(fanout, monkeypatch) -> None:
    from shared.jobs import checkpoint_store
    from tests.framework.fanout_sample import Begin
    from tests.framework.segment_sample import output
    from tests.framework.test_fanout import drain as drain_members
    from tests.framework.test_fanout_segments import configure

    changed, owner, segmented = await configure(fanout)
    changed = replace(changed, complete_by=DailyTime(daily_time(9, 30)), on_overdue="pause")
    fanout.catalog = fanout.queue.catalog = fanout.runtime.catalog = Catalog(
        [replace(owner, pipelines=(changed,)), segmented]
    )
    fanout.queue.pipelines.catalog = fanout.catalog
    original = checkpoint_store.load

    # 已提交第一批后才使周期逾期，第二批不进入操作，不依赖时间猜测。
    async def due_after_commit(database, job_id):
        loaded = await original(database, job_id)
        if loaded[0] == 1:
            await check(fanout.queue, datetime(2020, 1, 2, tzinfo=UTC).timestamp())
        return loaded

    monkeypatch.setattr(checkpoint_store, "load", due_after_commit)
    request = StartRequest[Begin](
        data=Begin(count=1), cycle_key="paused-batch", period=datetime(2020, 1, 1, tzinfo=UTC)
    )
    run_id = await fanout.runtime.submit(
        changed.start, changed.start.input(request=request), caller=CALLER
    )
    # 每轮维护会发现过去时间，先用操作领取执行到段边界，不预先调用维护器。
    import time

    from shared.jobs.worker import Worker, WorkerOptions

    worker = Worker(fanout.runtime, fanout.queue, [], WorkerOptions())
    for _ in range(3):
        ticket = await fanout.queue.claim(time.time())
        assert ticket is not None
        await worker.execute(ticket)
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 5000
        assert await connection.scalar(select(runs.c.state)) == "overdue_paused"
    monkeypatch.setattr(checkpoint_store, "load", original)
    await resume(fanout.database, fanout.catalog, run_id)
    assert (await drain_members(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 15000
