"""
后台任务测试：登记与完成、重复请求、排队上限、重试、执行期限过期、过期尝试不能覆盖新结果、
版本不符、定时计划不重复登记、worker 主循环。
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.setup.build import Services
from shared.access.caller import DEVELOPER, SYSTEM
from shared.errors.framework import DuplicateRequest, QueueFull
from shared.jobs.plan import Schedule
from shared.jobs.schedule import Scheduler, latest_slot
from shared.jobs.tables import jobs
from shared.jobs.views import get_job
from shared.jobs.worker import Worker, WorkerOptions
from tests.framework.sample_modules import CalcInput, SlowInput, calc, slow
from tests.framework.test_runner import count_notes

pytestmark = pytest.mark.anyio


# 组装一个 worker。
def make_worker(services: Services) -> Worker:
    options = WorkerOptions(concurrency=2, poll_seconds=0.02, shutdown_seconds=1)
    return Worker(services.runtime, services.queue, services.settings.api_keys, options)


# 领取并执行一个任务。
async def work_once(services: Services) -> str:
    ticket = await services.queue.claim(time.time())
    assert ticket is not None
    await make_worker(services).execute(ticket)
    return ticket.id


# 退出等待超时后，必须等在途任务的清理完成，调用方才可以关闭服务。
async def test_worker_drain_waits_for_cancelled_cleanup(sample: Services) -> None:
    worker = make_worker(sample)
    worker.options.shutdown_seconds = 0
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    # 模拟持有资源的任务，取消后需要异步归还资源。
    async def running() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    task = asyncio.create_task(running())
    worker.tasks.add(task)
    task.add_done_callback(worker.tasks.discard)
    await started.wait()
    draining = asyncio.create_task(worker.drain())
    try:
        await asyncio.wait_for(cleaning.wait(), 1)
        assert not draining.done() and not cleaned.is_set()
        release.set()
        await asyncio.wait_for(draining, 1)
        assert task.cancelled() and cleaned.is_set() and not worker.tasks
    finally:
        release.set()
        await asyncio.gather(task, draining, return_exceptions=True)


# 等待期间正常完成的任务保持成功结果。
async def test_worker_drain_keeps_completed_task(sample: Services) -> None:
    worker = make_worker(sample)
    release = asyncio.Event()

    # 模拟等待期间正常结束的业务任务。
    async def running() -> None:
        await release.wait()

    task = asyncio.create_task(running())
    worker.tasks.add(task)
    draining = asyncio.create_task(worker.drain())
    release.set()
    await asyncio.wait_for(draining, 1)
    assert task.done() and not task.cancelled() and task.result() is None


# 普通异常不会被当作取消吞掉；其余任务仍要完成清理后再报错。
async def test_worker_drain_reports_error_after_cleanup(sample: Services) -> None:
    worker = make_worker(sample)
    worker.options.shutdown_seconds = 0
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    # 模拟一个清理过程中失败的任务。
    async def failed() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            raise RuntimeError("清理失败")

    # 另一个任务仍在归还资源，错误必须等它结束后再抛出。
    async def running() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    tasks = [asyncio.create_task(failed()), asyncio.create_task(running())]
    worker.tasks.update(tasks)
    await started.wait()
    draining = asyncio.create_task(worker.drain())
    try:
        await asyncio.wait_for(cleaning.wait(), 1)
        assert not draining.done()
        release.set()
        with pytest.raises(RuntimeError, match="清理失败"):
            await asyncio.wait_for(draining, 1)
        assert cleaned.is_set() and all(task.done() for task in tasks)
    finally:
        release.set()
        await asyncio.gather(*tasks, draining, return_exceptions=True)


# 执行任务结束前，也要等待续期子任务归还自己的资源。
async def test_worker_execute_waits_for_heartbeat_cleanup(
    sample: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    ticket = await sample.queue.claim(time.time())
    assert ticket is not None
    worker = make_worker(sample)
    started, cleaned = asyncio.Event(), asyncio.Event()

    # 续期任务取消时异步释放连接。
    async def keep_lease(*args: object) -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    # 等续期任务启动后，模拟业务任务已经完成。
    async def run_job(*args: object) -> None:
        await started.wait()

    monkeypatch.setattr(worker, "keep_lease", keep_lease)
    monkeypatch.setattr(worker, "run_job", run_job)
    await worker.execute(ticket)
    assert cleaned.is_set()


# 登记的任务被执行后，业务写入和任务完成状态一起提交。
async def test_job_runs_and_finishes(sample: Services) -> None:
    job_id = await sample.runtime.submit(calc, CalcInput(amount=Decimal("8")), caller=DEVELOPER)
    await work_once(sample)
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "done" and job.result == {"total": "8", "saved": 1}
    assert job.last_run_id and await count_notes(sample) == 1


# 同一个请求编号重复登记返回原任务；内容不同时报冲突。
async def test_idempotency_key(sample: Services) -> None:
    first = await sample.runtime.submit(
        calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER, key="k"
    )
    again = await sample.runtime.submit(
        calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER, key="k"
    )
    assert first == again
    with pytest.raises(DuplicateRequest):
        await sample.runtime.submit(calc, CalcInput(amount=Decimal("2")), caller=DEVELOPER, key="k")


# 排队数量达到上限时拒绝新任务；完成后名额释放。
async def test_queue_limit(sample: Services) -> None:
    for mark in ("a", "b"):
        await sample.runtime.submit(slow, SlowInput(mark=mark), caller=DEVELOPER)
    with pytest.raises(QueueFull):
        await sample.runtime.submit(slow, SlowInput(mark="c"), caller=DEVELOPER)
    await work_once(sample)
    await sample.runtime.submit(slow, SlowInput(mark="c"), caller=DEVELOPER)


# 暂时故障按声明重试，次数用完后标为失败。
async def test_retry_then_fail(sample: Services) -> None:
    job_id = await sample.runtime.submit(
        calc, CalcInput(amount=Decimal("1"), fail_at="busy"), caller=DEVELOPER
    )
    await work_once(sample)
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "waiting_retry" and job.error_code == "sample_busy"
    await work_once(sample)
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "failed" and job.attempt == 2


# 程序异常不重试，直接标为失败并留下运行编号。
async def test_bug_is_not_retried(sample: Services) -> None:
    job_id = await sample.runtime.submit(
        calc, CalcInput(amount=Decimal("1"), fail_at="total"), caller=DEVELOPER
    )
    await work_once(sample)
    job = await get_job(sample.database, job_id)
    assert (
        job is not None
        and job.state == "failed"
        and job.error_code == "ValueError"
        and job.last_run_id
    )


# 执行期限过期：可安全重复的任务重新排队，其他任务标为结果待确认。
async def test_expired_lease(sample: Services) -> None:
    safe = await sample.runtime.submit(slow, SlowInput(mark="x"), caller=DEVELOPER)
    unsafe = await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    for _ in range(2):
        await sample.queue.claim(time.time())
    async with sample.database.write() as connection:
        await connection.execute(update(jobs).values(lease_until=time.time() - 1))
    assert await sample.queue.reclaim(time.time()) == 2
    assert (await get_job(sample.database, safe)).state == "waiting_retry"  # type: ignore[union-attr]
    assert (await get_job(sample.database, unsafe)).state == "unknown"  # type: ignore[union-attr]


# 过期的尝试不能覆盖新尝试：它的业务写入被撤销。
async def test_stale_attempt_is_rolled_back(sample: Services) -> None:
    job_id = await sample.runtime.submit(slow, SlowInput(mark="x"), caller=DEVELOPER)
    old = await sample.queue.claim(time.time())
    async with sample.database.write() as connection:
        await connection.execute(update(jobs).values(lease_until=time.time() - 1))
    await sample.queue.reclaim(time.time())
    new = await sample.queue.claim(time.time())
    assert old is not None and new is not None and new.attempt == 2
    await make_worker(sample).execute(old)
    assert await count_notes(sample) == 0
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "running" and job.attempt == 2


# 登记时的模块版本与当前不同，任务等待人工确认，不按新规则执行。
async def test_version_change_blocks(sample: Services) -> None:
    job_id = await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    async with sample.database.write() as connection:
        await connection.execute(update(jobs).values(module_version="0"))
    await work_once(sample)
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "blocked" and await count_notes(sample) == 0


# 定时计划在同一时段只登记一次，多个 worker 同时计算也一样。
async def test_schedule_is_idempotent(sample: Services) -> None:
    timer = Schedule(
        "every_minute", "每分钟", slow, SlowInput(mark="t"), every=timedelta(minutes=1)
    )
    now = time.time()
    first = Scheduler([timer], sample.queue, sample.database)
    second = Scheduler([timer], sample.queue, sample.database)
    assert await first.tick(now) == 1
    assert await first.tick(now) == 0
    await second.tick(now)
    async with sample.database.read() as connection:
        rows = (await connection.execute(jobs.select())).mappings().all()
    assert len(rows) == 1 and json.loads(rows[0]["caller_json"])["id"] == SYSTEM.id


# 队列满导致定时任务登记失败时，释放容量后仍能补上当前时段。
async def test_schedule_retries_after_queue_capacity_returns(sample: Services) -> None:
    # 同一时段登记失败后，容量恢复就应补上；成功后仍只登记一次。
    for mark in ("a", "b"):
        await sample.runtime.submit(slow, SlowInput(mark=mark), caller=DEVELOPER)
    timer = Schedule(
        "hourly",
        "每小时",
        slow,
        SlowInput(mark="scheduled"),
        every=timedelta(hours=1),
        missed="latest",
    )
    scheduler = Scheduler([timer], sample.queue, sample.database)
    now = datetime(2026, 10, 1, 0, 0, tzinfo=UTC).timestamp()
    assert await scheduler.tick(now) == 0
    await work_once(sample)
    assert await scheduler.tick(now + 1) == 1
    assert await scheduler.tick(now + 2) == 0


# 每日计划的最近时段：当天时间未到时取前一天。
def test_latest_daily_slot() -> None:
    from datetime import time as clock

    timer = Schedule("daily", "每天", slow, SlowInput(mark="t"), daily_at=clock(2, 0))
    before = datetime(2026, 9, 23, 17, 0, tzinfo=UTC)
    assert latest_slot(timer, before).isoformat() == "2026-09-23T02:00:00+08:00"
    early = datetime(2026, 9, 22, 17, 0, tzinfo=UTC)
    assert latest_slot(timer, early).isoformat() == "2026-09-22T02:00:00+08:00"


# worker 主循环领取并完成任务，收到停止信号后退出。
async def test_worker_loop(sample: Services) -> None:
    job_id = await sample.runtime.submit(slow, SlowInput(mark="loop"), caller=DEVELOPER)
    stop = asyncio.Event()
    running = asyncio.create_task(make_worker(sample).run(stop))
    for _ in range(100):
        job = await get_job(sample.database, job_id)
        if job is not None and job.state == "done":
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(running, 2)
    assert job is not None and job.state == "done"


# 登记任务的服务密钥被删除后，任务不再执行。
async def test_removed_key_stops_job(sample: Services) -> None:
    job_id = await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    async with sample.database.write() as connection:
        record = '{"id": "key:gone", "kind": "service", "name": "gone", "permissions": ["*"]}'
        await connection.execute(update(jobs).values(caller_json=record))
    await work_once(sample)
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "failed" and job.error_code == "not_allowed"
