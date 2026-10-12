"""
受控等待、校时和截止使用事件循环真实取消，但不等待真实业务秒数。
"""

import asyncio

import pytest

from shared.timing.clock import FakeClock

pytestmark = pytest.mark.anyio


# 业务校时不改变单调预算，等待只在主动推进足够时间后结束。
async def test_controlled_sleep_and_wall_adjustment() -> None:
    clock = FakeClock(100)
    sleeper = asyncio.create_task(clock.sleep(10))
    await asyncio.sleep(0)
    clock.advance(9)
    assert not sleeper.done() and clock.now() == 109
    clock.set_wall(50)
    assert clock.monotonic() == 9
    clock.advance(1)
    await sleeper
    assert clock.now() == 51 and clock.monotonic() == 10


# 超时真正取消未完成操作，不把完成状态写成成功。
async def test_controlled_deadline_cancels_work() -> None:
    clock = FakeClock()
    started, cancelled = asyncio.Event(), asyncio.Event()

    # 业务等待模拟外部响应，截止后需要收到取消。
    async def work() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    running = asyncio.create_task(clock.run(work(), deadline=5))
    await started.wait()
    await asyncio.sleep(0)
    clock.advance(5)
    with pytest.raises(TimeoutError):
        await running
    assert cancelled.is_set()


# 操作提前完成，计时等待会被清理，不需要把时间推进到截止。
async def test_completed_work_does_not_wait_for_deadline() -> None:
    clock = FakeClock()

    # 一个即时纯计算结果。
    async def work() -> int:
        return 7

    assert await clock.run(work(), deadline=100) == 7
    assert clock.monotonic() == 0
    assert not clock.waiters
