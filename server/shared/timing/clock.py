import asyncio
import heapq
import math
import time
from collections.abc import Awaitable
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    async def run[Result](self, awaitable: Awaitable[Result], *, deadline: float) -> Result: ...


class RealClock:
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0, seconds))

    async def run[Result](self, awaitable: Awaitable[Result], *, deadline: float) -> Result:
        async with asyncio.timeout(deadline - self.monotonic()):
            return await awaitable


class FakeClock:
    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.wall, self.tick = now, 0.0
        self.waiters: list[tuple[float, int, asyncio.Future[None]]] = []
        self.sequence = 0

    def now(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.tick

    def advance(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("受控时间只能向前推进有限秒数")
        self.wall += seconds
        self.tick += seconds
        while self.waiters and self.waiters[0][0] <= self.tick:
            _, _, waiter = heapq.heappop(self.waiters)
            if not waiter.done():
                waiter.set_result(None)

    def set_wall(self, timestamp: float) -> None:
        if not math.isfinite(timestamp):
            raise ValueError("业务时间必须为有限时间戳")
        self.wall = timestamp

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        waiter = asyncio.get_running_loop().create_future()
        self.sequence += 1
        heapq.heappush(self.waiters, (self.tick + seconds, self.sequence, waiter))
        try:
            await waiter
        finally:
            self.waiters = [item for item in self.waiters if item[2] is not waiter]
            heapq.heapify(self.waiters)

    async def run[Result](self, awaitable: Awaitable[Result], *, deadline: float) -> Result:
        operation = asyncio.ensure_future(awaitable)
        timer = asyncio.create_task(self.sleep(deadline - self.tick))
        try:
            await asyncio.wait({operation, timer}, return_when=asyncio.FIRST_COMPLETED)
            if operation.done():
                return operation.result()
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            raise TimeoutError("受控执行预算耗尽")
        finally:
            operation.cancel()
            timer.cancel()
            await asyncio.gather(operation, timer, return_exceptions=True)


def clock_kind(clock: Clock) -> str:
    if isinstance(clock, FakeClock) or getattr(clock, "simulated", False):
        return "simulated"
    return "real" if isinstance(clock, RealClock) else "custom"
