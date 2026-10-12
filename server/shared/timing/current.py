"""
同一次执行的框架辅助函数继承时钟上下文，不用全局可变时间，也不让并发应用互相改变时钟。
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Concatenate, Protocol

from shared.timing.clock import Clock, RealClock

CURRENT: ContextVar[Clock | None] = ContextVar("application_clock", default=None)
DEFAULT_CLOCK = RealClock()


# 需要执行预算的框架工具读取当前上下文；默认时钟本身没有可变业务时间。
def current_clock() -> Clock:
    return CURRENT.get() or DEFAULT_CLOCK


# 框架执行对象公开同一个时钟，子辅助函数无需重复传递配置。
class ClockOwner(Protocol):
    # 实际时钟由产品组装或测试注入。
    @property
    def clock(self) -> Clock: ...


# 上下文只影响当前任务及其子任务，退出或取消都恢复原来的时钟。
@contextmanager
def use_clock(clock: Clock) -> Iterator[None]:
    token = CURRENT.set(clock)
    try:
        yield
    finally:
        CURRENT.reset(token)


# 框架入口方法绑定自己的时钟，业务步骤仍显式接收clock参数。
def clocked[Owner: ClockOwner, **Params, Result](
    func: Callable[Concatenate[Owner, Params], Awaitable[Result]],
) -> Callable[Concatenate[Owner, Params], Coroutine[Any, Any, Result]]:
    # 保留原始函数名与注释位置，反射和调用签名不改变。
    @wraps(func)
    async def wrapped(self: Owner, /, *args: Params.args, **kwargs: Params.kwargs) -> Result:
        with use_clock(self.clock):
            return await func(self, *args, **kwargs)

    return wrapped


# 持久业务时间来自当前应用，不从机器时钟重新猜测。
def now() -> float:
    return (CURRENT.get() or DEFAULT_CLOCK).now()


# 消耗计时使用当前应用的单调时间。
def monotonic() -> float:
    return (CURRENT.get() or DEFAULT_CLOCK).monotonic()


# 框架重试和冷却等待可被测试主动推进。
async def sleep(seconds: float) -> None:
    await (CURRENT.get() or DEFAULT_CLOCK).sleep(seconds)


# 停止信号与冷却等待竞争，受控时钟下不需要真实睡眠。
async def wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    clock = CURRENT.get() or DEFAULT_CLOCK
    try:
        await clock.run(stop.wait(), deadline=clock.monotonic() + seconds)
    except TimeoutError:
        return
