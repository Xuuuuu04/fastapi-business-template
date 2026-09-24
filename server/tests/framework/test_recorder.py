"""
运行记录写入器在故障时的行为：记录丢失要计数、保存失败不影响业务、
长时间没有进展的运行标为“失去联系”，后台循环能把缓冲中的记录写出去。
"""

import asyncio
import time

import pytest

import shared.records.recorder as recorder_file
from shared.records.models import RunRecord
from shared.records.recorder import LOST_AFTER_SECONDS, Recorder
from shared.records.stores import MemoryRunStore, RunFilter


class SlowStore(MemoryRunStore):
    immediate = False

    # 保存时可以按需要抛出异常，模拟数据库不可用。
    def __init__(self, fail: bool = False) -> None:
        super().__init__(100)
        self.fail = fail

    # 模拟保存；fail 为真时报错。
    async def save(self, runs: list[RunRecord]) -> None:
        if self.fail:
            raise ConnectionError("数据库不可用")
        await super().save(runs)


# 生成一条测试用运行记录。
def record(run_id: str, *, status: str = "ok", root_id: str = "") -> RunRecord:
    return RunRecord(
        id=run_id,
        root_id=root_id or run_id,
        parent_id="",
        parent_step="",
        contract="sample_calc.calc",
        title="计算",
        module="sample_calc",
        module_version="1",
        code_version="test",
        request_id="",
        job_id="",
        caller="tester",
        started_at=time.time(),
        status=status,
    )


# 缓冲区满时丢弃并计数；保存失败时计数，不向业务抛出异常。
@pytest.mark.anyio
async def test_buffer_full_and_save_failure_are_counted() -> None:
    full = Recorder(SlowStore(), buffer=1)
    await full.finish(record("a"))
    await full.finish(record("b"))
    assert full.state().waiting == 1 and full.state().dropped == 1

    broken = Recorder(SlowStore(fail=True), buffer=10)
    await broken.finish(record("c"))
    await broken.flush()
    assert broken.state().failures == 1 and broken.state().waiting == 0


# 生成摘要出错时照样保存记录，只把失败计数。
@pytest.mark.anyio
async def test_summary_failure_still_saves(monkeypatch: pytest.MonkeyPatch) -> None:
    # 模拟摘要程序出错。
    def broken(run: RunRecord) -> str:
        raise ValueError("摘要出错")

    monkeypatch.setattr(recorder_file, "summarize", broken)
    store = MemoryRunStore(10)
    recorder = Recorder(store)
    await recorder.finish(record("d"))
    assert recorder.state().failures == 1
    assert await store.get("d") is not None


# 超过期限没有进展的运行在查询结果中标为“失去联系”，原记录不被改动。
@pytest.mark.anyio
async def test_stale_run_is_reported_lost() -> None:
    recorder = Recorder(MemoryRunStore(10))
    stale, fresh = record("e", status="running"), record("f", status="running", root_id="e")
    recorder.start(stale)
    recorder.start(fresh)
    stale.updated_at = time.time() - LOST_AFTER_SECONDS - 1
    found = await recorder.get("e")
    assert found is not None and found.status == "lost" and "失去联系" in found.summary
    assert stale.status == "running"
    assert [run.status for run in await recorder.tree("e")] == ["lost", "running"]
    listed = await recorder.recent(RunFilter(), 10)
    assert {run.id for run in listed} == {"e", "f"}


# 后台循环收到新记录后把缓冲写入保存位置；缓冲中的记录在写入前也能查到。
@pytest.mark.anyio
async def test_background_flush_writes_waiting_runs() -> None:
    store = SlowStore()
    recorder = Recorder(store)
    await recorder.finish(record("g"))
    assert await recorder.get("g") is not None and await store.get("g") is None
    task = asyncio.create_task(recorder.run_forever())
    try:
        for _ in range(50):
            if await store.get("g") is not None:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
    assert await store.get("g") is not None and recorder.state().waiting == 0


class PausingStore(SlowStore):
    # 保存前先等待一会，模拟停止时正好有一批记录在写入。
    async def save(self, runs: list[RunRecord]) -> None:
        await asyncio.sleep(0.05)
        await super().save(runs)


# 停止后台写入时，正在写入的一批和还在缓冲中的记录都保存下来，不因取消而丢失。
@pytest.mark.anyio
async def test_stop_keeps_runs_being_written() -> None:
    store = PausingStore()
    recorder = Recorder(store)
    writer = asyncio.create_task(recorder.run_forever())
    await recorder.finish(record("first"))
    await asyncio.sleep(0.01)
    await recorder.finish(record("second"))
    await recorder.stop(writer)
    assert writer.done()
    assert {run.id for run in await store.recent(RunFilter(), 10)} == {"first", "second"}
