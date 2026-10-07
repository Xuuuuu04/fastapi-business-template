"""
耗时纯计算的有界准入。请求取消只停止等待，额度随真实线程工作结束归还。
同步函数无法安全强制停止，函数自身必须能在有限时间内结束。
"""

import asyncio
import threading
from collections.abc import Callable
from typing import Any

from shared.errors.framework import TooBusy


# 同一个执行器限制提交中的耗时计算，取消不能制造新的线程队列额度。
class HeavySteps:
    # 记录有限额度、实际任务和取消标记。
    def __init__(self, concurrency: int = 4) -> None:
        self.concurrency = concurrency
        self.changed = asyncio.Event()
        self.running: dict[asyncio.Task[Any], threading.Event] = {}
        self.closing = False

    # 准入等待沿用操作的超时范围，真实线程没有结束时不释放额度。
    async def run(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        while len(self.running) >= self.concurrency and not self.closing:
            self.changed.clear()
            await self.changed.wait()
        if self.closing:
            raise TooBusy("耗时计算正在停止，请稍后再试")
        cancelled = threading.Event()

        # 还未开始的取消计算被线程取出后直接跳过，不访问已经结束的流程数据。
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

    # 线程完成后才归还额度；无人等待的失败也被读取，不留下未处理异常。
    def finished(self, task: asyncio.Task[Any]) -> None:
        self.running.pop(task, None)
        self.changed.set()
        if not task.cancelled():
            task.exception()

    # 停止新增计算，未开始的工作跳过，有限等待已有工作完成。
    async def close(self, seconds: float = 20) -> None:
        self.closing = True
        self.changed.set()
        for cancelled in self.running.values():
            cancelled.set()
        if self.running:
            await asyncio.wait(tuple(self.running), timeout=seconds)
