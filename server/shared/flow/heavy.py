import asyncio
import threading
from collections.abc import Callable
from typing import Any

from shared.errors.framework import TooBusy


class HeavySteps:
    def __init__(self, concurrency: int = 4) -> None:
        self.concurrency = concurrency
        self.changed = asyncio.Event()
        self.running: dict[asyncio.Task[Any], threading.Event] = {}
        self.closing = False

    async def run(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        while len(self.running) >= self.concurrency and not self.closing:
            self.changed.clear()
            await self.changed.wait()
        if self.closing:
            raise TooBusy("耗时计算正在停止，请稍后再试")
        cancelled = threading.Event()

        def work() -> Any:
            return None if cancelled.is_set() else function(*args, **kwargs)

        task = asyncio.create_task(asyncio.to_thread(work))
        self.running[task] = cancelled
        task.add_done_callback(self.finished)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    def finished(self, task: asyncio.Task[Any]) -> None:
        self.running.pop(task, None)
        self.changed.set()
        if not task.cancelled():
            task.exception()

    async def close(self, seconds: float = 20) -> None:
        self.closing = True
        self.changed.set()
        for cancelled in self.running.values():
            cancelled.set()
        if self.running:
            await asyncio.wait(tuple(self.running), timeout=seconds)
