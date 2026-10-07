"""
后台进程退出时的任务与资源清理测试。
检查取消后等待清理、正常完成、清理异常和续期子任务退出的顺序。
"""

import asyncio
import time
from decimal import Decimal

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from tests.framework.sample_modules import CalcInput, calc
from tests.framework.test_jobs import make_worker

pytestmark = pytest.mark.anyio


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
