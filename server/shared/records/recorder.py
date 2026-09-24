"""
运行记录器：保存正在执行的运行，结束后交给保存位置。
记录器自身出错不影响业务：保存失败、缓冲已满时只计数，并在查询时标明记录不完整。
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, replace

from shared.records.models import RunRecord
from shared.records.stores import RunFilter, RunStore, matches
from shared.records.summary import summarize

log = logging.getLogger("server.records")

LOST_AFTER_SECONDS = 300


@dataclass(frozen=True)
class RecorderState:
    active: int
    waiting: int
    dropped: int
    failures: int
    stored_dropped: int


class Recorder:
    # 设置保存位置和等待写入的缓冲上限。
    def __init__(self, store: RunStore, *, buffer: int = 5000) -> None:
        self.store = store
        self.buffer = buffer
        self.active: dict[str, RunRecord] = {}
        self.waiting: deque[RunRecord] = deque()
        self.dropped = 0
        self.failures = 0
        self.wakeup = asyncio.Event()
        self.closing = False

    # 登记一次开始执行的运行。
    def start(self, run: RunRecord) -> None:
        run.updated_at = time.time()
        self.active[run.id] = run

    # 结束一次运行：生成中文摘要并交给保存位置。
    async def finish(self, run: RunRecord) -> None:
        self.active.pop(run.id, None)
        try:
            run.summary = summarize(run)
        except Exception:
            self.failures += 1
            log.exception("run_summary_failed run_id=%s", run.id)
        if self.store.immediate:
            await self.save([run])
        elif len(self.waiting) >= self.buffer:
            self.dropped += 1
        else:
            self.waiting.append(run)
            self.wakeup.set()

    # 保存一批记录；失败只计数和写日志。
    async def save(self, runs: list[RunRecord]) -> None:
        try:
            await self.store.save(runs)
        except Exception:
            self.failures += len(runs)
            log.exception("run_records_save_failed count=%s", len(runs))

    # 把缓冲中的记录全部写入保存位置。
    async def flush(self) -> None:
        while self.waiting:
            batch = [self.waiting.popleft() for _ in range(min(100, len(self.waiting)))]
            await self.save(batch)

    # 后台循环：有新记录时批量写入；收到停止信号时写完剩余记录再退出。
    async def run_forever(self) -> None:
        while True:
            await self.wakeup.wait()
            self.wakeup.clear()
            await self.flush()
            if self.closing:
                return
            await asyncio.sleep(0.2)

    # 停止后台循环：不直接取消，避免正在写入的一批记录丢失；超时仍未写完时记日志。
    async def stop(self, writer: "asyncio.Task[None]", seconds: float = 10.0) -> None:
        self.closing = True
        self.wakeup.set()
        try:
            await asyncio.wait_for(writer, seconds)
        except TimeoutError:
            log.error("run_records_stop_timeout waiting=%s", len(self.waiting))

    # 按编号查找记录：先查正在执行和等待写入的，再查保存位置。
    async def get(self, run_id: str) -> RunRecord | None:
        found = self.active.get(run_id) or next(
            (run for run in self.waiting if run.id == run_id), None
        )
        if found is not None:
            return mark_lost(found)
        return await self.store.get(run_id)

    # 读取同一次最外层运行下的全部记录，包括仍在执行的。
    async def tree(self, root_id: str) -> list[RunRecord]:
        stored = {run.id: run for run in await self.store.tree(root_id)}
        for run in [*self.waiting, *self.active.values()]:
            if run.root_id == root_id:
                stored[run.id] = mark_lost(run)
        return sorted(stored.values(), key=lambda run: run.started_at)

    # 按条件读取最近的记录，正在执行的排在前面。
    async def recent(self, rules: RunFilter, limit: int) -> list[RunRecord]:
        live = [mark_lost(run) for run in self.active.values() if matches(run, rules)]
        pending = [run for run in reversed(self.waiting) if matches(run, rules)]
        found: dict[str, RunRecord] = {}
        for run in [*live, *pending, *await self.store.recent(rules, limit)]:
            found.setdefault(run.id, run)
        return list(found.values())[:limit]

    # 返回记录器当前状态，用于判断记录是否完整。
    def state(self) -> RecorderState:
        return RecorderState(
            active=len(self.active),
            waiting=len(self.waiting),
            dropped=self.dropped,
            failures=self.failures,
            stored_dropped=self.store.dropped,
        )

    # 查询已保存的运行统计；等待写入的记录仍由 state() 单独报告。
    async def stats(self, since: float, module: str = "") -> list[dict[str, object]]:
        return await self.store.stats(since, module)


# 返回运行记录的查询副本：更新已用时间，长时间没有进展的标为“失去联系”。
def mark_lost(run: RunRecord) -> RunRecord:
    if run.status != "running":
        return run
    now = time.time()
    status = "lost" if now - run.updated_at > LOST_AFTER_SECONDS else "running"
    copied = replace(run, status=status, elapsed_ms=(now - run.started_at) * 1000)
    copied.summary = summarize(copied)
    return copied
