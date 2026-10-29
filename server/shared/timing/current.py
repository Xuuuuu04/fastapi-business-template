import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Concatenate, Protocol

from shared.timing.clock import Clock, RealClock

CURRENT: ContextVar[Clock | None] = ContextVar("application_clock", default=None)
DEFAULT_CLOCK = RealClock()


def current_clock() -> Clock:
    return CURRENT.get() or DEFAULT_CLOCK


class ClockOwner(Protocol):
    @property
    def clock(self) -> Clock: ...


@contextmanager
def use_clock(clock: Clock) -> Iterator[None]:
    token = CURRENT.set(clock)
    try:
        yield
    finally:
        CURRENT.reset(token)


def clocked[Owner: ClockOwner, **Params, Result](
    func: Callable[Concatenate[Owner, Params], Awaitable[Result]],
) -> Callable[Concatenate[Owner, Params], Coroutine[Any, Any, Result]]:
    @wraps(func)
    async def wrapped(self: Owner, /, *args: Params.args, **kwargs: Params.kwargs) -> Result:
        with use_clock(self.clock):
            return await func(self, *args, **kwargs)

    return wrapped


def now() -> float:
    return (CURRENT.get() or DEFAULT_CLOCK).now()


def monotonic() -> float:
    return (CURRENT.get() or DEFAULT_CLOCK).monotonic()


async def sleep(seconds: float) -> None:
    await (CURRENT.get() or DEFAULT_CLOCK).sleep(seconds)


async def wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    clock = CURRENT.get() or DEFAULT_CLOCK
    try:
        await clock.run(stop.wait(), deadline=clock.monotonic() + seconds)
    except TimeoutError:
        return
