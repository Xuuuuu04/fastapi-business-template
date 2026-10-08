"""
分段任务在提交边界响应停止，批间续租，图与任务摘要显示恢复位置及累计行数。
"""

import asyncio
import time

import pytest
from sqlalchemy import update

from app.setup.build import Services
from shared.graphs.observed import run_graph, run_report
from shared.graphs.static import flow_graph
from shared.jobs.checkpoint_store import list_segments, progress
from shared.jobs.tables import jobs
from shared.jobs.views import get_job
from shared.jobs.worker import Worker, WorkerOptions
from shared.records.stores import RunFilter
from tests.framework.segment_sample import BatchStore, batch
from tests.framework.test_segmented_jobs import execute, submit
from tests.framework.test_segmented_jobs import segmented as segmented

pytestmark = pytest.mark.anyio


# 停止等待短于本批耗时也不取消当前批；结束后重新领取可继续剩余数据。
async def test_stop_finishes_current_batch(segmented: Services, monkeypatch, caplog) -> None:
    caplog.set_level("INFO", logger="server.jobs")
    job_id = await submit(segmented, total=15000)
    entered, release = asyncio.Event(), asyncio.Event()
    original = BatchStore.save

    # 第一批实际写入后暂停，模拟尚未处理完的一批。
    async def wait_first(self, start, end):
        count = await original(self, start, end)
        if start == 0:
            entered.set()
            await release.wait()
        return count

    monkeypatch.setattr(BatchStore, "save", wait_first)
    worker = Worker(
        segmented.runtime,
        segmented.queue,
        [],
        WorkerOptions(
            concurrency=1,
            poll_seconds=0.01,
            shutdown_seconds=0.01,
        ),
    )
    stop = asyncio.Event()
    running = asyncio.create_task(worker.run(stop))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        stop.set()
        await asyncio.sleep(0.05)
        assert not running.done()
        release.set()
        await asyncio.wait_for(running, 3)
    finally:
        stop.set()
        release.set()
        await asyncio.wait_for(running, 3)
    assert any("cancelled=0" in record.message for record in caplog.records)
    job = await get_job(segmented.database, job_id)
    saved = await progress(segmented.database, job_id)
    assert job is not None and job.state == "waiting_retry"
    assert saved is not None and saved["cursor"] == {"after": 5000}
    assert saved["total_rows"] == 5000 and saved["committed_batches"] == 1
    monkeypatch.setattr(BatchStore, "save", original)
    await execute(segmented)
    assert (await progress(segmented.database, job_id))["total_rows"] == 15000


# 每批开始前有效续租；已经过期的领取不能通过续租复活。
async def test_each_batch_renews_valid_lease(segmented: Services, monkeypatch) -> None:
    await submit(segmented, total=15000)
    original = segmented.queue.extend
    renewals = []

    # 观察真实续租调用，不替换其尝试和租约检查。
    async def extend(ticket, until, *, require_current=False):
        renewals.append(require_current)
        return await original(ticket, until, require_current=require_current)

    monkeypatch.setattr(segmented.queue, "extend", extend)
    ticket = await segmented.queue.claim(time.time())
    assert ticket is not None
    await execute(segmented, ticket)
    assert len(renewals) >= 3 and all(renewals)
    async with segmented.database.write() as connection:
        await connection.execute(update(jobs).values(state="running", lease_until=time.time() - 1))
    # 手工改变状态仅为了验证过期续租，不能推进任何业务游标。
    assert not await original(ticket, time.time() + 60, require_current=True)


# 摘要优先：任务持久化数据与运行图都能查看游标、行数、耗时和累计数量。
async def test_segment_graph_and_durable_summary(segmented: Services) -> None:
    job_id = await submit(segmented, total=10000)
    await execute(segmented)
    saved = await progress(segmented.database, job_id)
    assert saved is not None and saved["cursor"] == {"after": 10000}
    assert saved["total_rows"] == 10000 and saved["last_batch"]["rows"] == 5000
    pages = await list_segments(segmented.database, job_id, after=0, limit=1)
    assert pages[0]["number"] == 1 and pages[0]["cursor"] == {"after": 5000}
    assert pages[0]["total_rows"] == 5000 and pages[0]["elapsed_ms"] > 0
    records = await segmented.runtime.recorder.recent(RunFilter(job_id=job_id), 10)
    final = next(run for run in records if run.segment_number == 2)
    assert "第2批" in run_graph([final]) and "累计10000行" in run_graph([final])
    assert "&quot;after&quot;: 10000}" in run_graph([final])
    assert "after" in run_report([final], final.id)
    assert "分段任务" in flow_graph(segmented.catalog.binding(batch))
