"""
耗时计算的实际线程生命周期与准入额度，不让超时积累无界排队。
"""

import asyncio
import threading
from contextvars import ContextVar

import pytest

from shared.errors.framework import TooBusy
from shared.flow.heavy import HeavySteps

pytestmark = pytest.mark.anyio


# 取消等待后仍保留真实线程额度，反复超时不能继续提交计算。
async def test_cancelled_calculation_holds_admission_until_finished() -> None:
    heavy = HeavySteps(1)
    started, release = threading.Event(), threading.Event()
    attempted = []

    # 合成可释放的耗时计算，测试结束前一定让线程退出。
    def blocking() -> None:
        started.set()
        release.wait(2)

    task = asyncio.create_task(heavy.run(blocking))
    try:
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        for _ in range(12):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.005):
                    await heavy.run(lambda: attempted.append(True))
        assert not attempted and len(heavy.running) == 1
    finally:
        release.set()
        await heavy.close(1)
    assert not heavy.running


# 正常结果、上下文变量和失败仍保持原语义，额度能被下一次计算使用。
async def test_heavy_result_context_and_failure_release() -> None:
    heavy = HeavySteps(1)
    marker = ContextVar("synthetic-heavy-context", default="unset")
    token = marker.set("request-context")
    try:
        assert await heavy.run(marker.get) == "request-context"

        # 程序失败继续交给流程处理，而非吞掉异常或返回空结果。
        def failed() -> None:
            raise ValueError("synthetic-only")

        with pytest.raises(ValueError):
            await heavy.run(failed)
        assert await heavy.run(lambda: 42) == 42
        assert not heavy.running
    finally:
        marker.reset(token)
        await heavy.close(1)


# 停止后不再接收新的计算，已有工作的取消额度不被复用。
async def test_closed_heavy_runner_rejects_new_work() -> None:
    heavy = HeavySteps(1)
    await heavy.close(0)
    with pytest.raises(TooBusy):
        await heavy.run(lambda: 1)


# 停止时立即唤醒已在准入等待的调用，不能等真实线程结束才拒绝。
async def test_close_wakes_waiting_admission_without_releasing_active_work() -> None:
    heavy = HeavySteps(1)
    started, release = threading.Event(), threading.Event()
    attempted = []

    # 合成仍然占用额度的同步计算，结束时释放测试线程。
    def blocking() -> None:
        started.set()
        release.wait(2)

    active = asyncio.create_task(heavy.run(blocking))
    waiting = None
    try:
        while not started.is_set():
            await asyncio.sleep(0.001)
        waiting = asyncio.create_task(heavy.run(lambda: attempted.append(True)))
        await asyncio.sleep(0)
        await heavy.close(0)
        with pytest.raises(TooBusy):
            await asyncio.wait_for(waiting, 0.1)
        assert not attempted and len(heavy.running) == 1
    finally:
        release.set()
        await asyncio.gather(active, *([waiting] if waiting else []), return_exceptions=True)
        await heavy.close(1)
