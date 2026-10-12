"""
业务时间和单调预算共用可注入时钟；受控时间通过推进唤醒等待，不依赖真实睡眠。
"""

import asyncio
import heapq
import math
import time
from collections.abc import Awaitable
from typing import Protocol


# 时钟统一业务时间、消耗计时与等待，进程重启只恢复业务截止，不恢复单调绝对值。
class Clock(Protocol):
    # UTC业务时间戳供持久任务与有效期使用。
    def now(self) -> float: ...

    # 单调时间仅用于当前进程预算与消耗计时。
    def monotonic(self) -> float: ...

    # 等待不持有数据库写事务。
    async def sleep(self, seconds: float) -> None: ...

    # 截止时取消当前等待，外部已经产生的效果仍需要单独恢复。
    async def run[Result](self, awaitable: Awaitable[Result], *, deadline: float) -> Result: ...


# 正式时钟保持现有asyncio取消语义，不为每个操作额外创建执行任务。
class RealClock:
    # 持久状态只保存UTC时间戳。
    def now(self) -> float:
        return time.time()

    # 系统校时不会让当前操作消耗倒退。
    def monotonic(self) -> float:
        return time.monotonic()

    # 正常等待交给事件循环。
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0, seconds))

    # 使用同一单调时钟执行截止，保持嵌套调用的取消传播。
    async def run[Result](self, awaitable: Awaitable[Result], *, deadline: float) -> Result:
        async with asyncio.timeout_at(deadline):
            return await awaitable


# 合成测试只在显式推进时唤醒等待，不自动改变其他流程的时间。
class FakeClock:
    # 默认业务时间是明确合成基准，单调时间从零开始。
    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.wall, self.tick = now, 0.0
        self.waiters: list[tuple[float, int, asyncio.Future[None]]] = []
        self.sequence = 0

    # 返回可推进的业务时间。
    def now(self) -> float:
        return self.wall

    # 单调计时不受业务校时影响。
    def monotonic(self) -> float:
        return self.tick

    # 同时推进业务和单调时间，已经取消的等待不会再次唤醒。
    def advance(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("受控时间只能向前推进有限秒数")
        self.wall += seconds
        self.tick += seconds
        while self.waiters and self.waiters[0][0] <= self.tick:
            _, _, waiter = heapq.heappop(self.waiters)
            if not waiter.done():
                waiter.set_result(None)

    # 校时只影响业务时间，不改变在途预算。
    def set_wall(self, timestamp: float) -> None:
        if not math.isfinite(timestamp):
            raise ValueError("业务时间必须为有限时间戳")
        self.wall = timestamp

    # 等待直到测试主动推进，零秒等待仍让出一次执行位置。
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

    # 执行与受控截止竞争，取消时清理两项等待，不留下后台任务。
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


# 运行观察区分真实、模拟与扩展时钟，模拟耗时不作为性能验收证据。
def clock_kind(clock: Clock) -> str:
    if isinstance(clock, FakeClock) or getattr(clock, "simulated", False):
        return "simulated"
    return "real" if isinstance(clock, RealClock) else "custom"
