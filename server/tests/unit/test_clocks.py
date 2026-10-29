import asyncio

import pytest

from shared.timing.clock import FakeClock, RealClock

pytestmark = pytest.mark.anyio


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


async def test_controlled_deadline_cancels_work() -> None:
    clock = FakeClock()
    started, cancelled = asyncio.Event(), asyncio.Event()

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


async def test_completed_work_does_not_wait_for_deadline() -> None:
    clock = FakeClock()

    async def work() -> int:
        return 7

    assert await clock.run(work(), deadline=100) == 7
    assert clock.monotonic() == 0
    assert not clock.waiters


class ShiftedLoop(asyncio.SelectorEventLoop):
    def time(self) -> float:
        return super().time() + 1000


def test_real_deadline_ignores_loop_clock_offset() -> None:
    clock, loop = RealClock(), ShiftedLoop()
    try:
        work = asyncio.sleep(0.01, "完成")
        assert loop.run_until_complete(clock.run(work, deadline=clock.monotonic() + 5)) == "完成"
        with pytest.raises(TimeoutError):
            slow = asyncio.sleep(5)
            loop.run_until_complete(clock.run(slow, deadline=clock.monotonic() + 0.01))
    finally:
        loop.close()
