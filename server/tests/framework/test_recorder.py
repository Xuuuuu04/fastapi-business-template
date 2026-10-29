import asyncio
import time

import pytest

import shared.records.recorder as recorder_file
from shared.records.models import RunRecord
from shared.records.recorder import LOST_AFTER_SECONDS, Recorder
from shared.records.stores import MemoryRunStore, RunFilter


class SlowStore(MemoryRunStore):
    immediate = False

    def __init__(self, fail: bool = False) -> None:
        super().__init__(100)
        self.fail = fail

    async def save(self, runs: list[RunRecord]) -> None:
        if self.fail:
            raise ConnectionError("数据库不可用")
        await super().save(runs)


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


@pytest.mark.anyio
async def test_summary_failure_still_saves(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(run: RunRecord) -> str:
        raise ValueError("摘要出错")

    monkeypatch.setattr(recorder_file, "summarize", broken)
    store = MemoryRunStore(10)
    recorder = Recorder(store)
    await recorder.finish(record("d"))
    assert recorder.state().failures == 1
    assert await store.get("d") is not None


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
    async def save(self, runs: list[RunRecord]) -> None:
        await asyncio.sleep(0.05)
        await super().save(runs)


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


@pytest.mark.anyio
async def test_progress_is_visible_to_another_recorder(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shared.db.database import Database
    from shared.records.models import StepRecord
    from shared.records.stores import SqlRunStore
    from tests.testing_app import reset_database

    await reset_database(settings.database_url)
    database = Database(settings.database_url)
    writer, reader = Recorder(SqlRunStore(database)), Recorder(SqlRunStore(database))
    run = record("progress", status="running")
    run.steps.append(
        StepRecord(
            "s1", "read_data", "读取数据", "read", "", "test.py:1", started_at=time.time() - 1
        )
    )
    writer.start(run)
    monkeypatch.setattr(recorder_file, "PROGRESS_SECONDS", 0.01)
    task = asyncio.create_task(writer.run_forever())
    try:
        async with asyncio.timeout(5):
            while await reader.get(run.id) is None:
                await asyncio.sleep(0.01)
        found = await reader.get(run.id)
        assert found is not None and found.status == "running"
        assert found.steps[0].title == "读取数据" and found.steps[0].elapsed_ms >= 1000
        assert await reader.stats(0) == []
        run.steps[0].status = "ok"
        run.status = "ok"
        await writer.finish(run)
        await writer.stop(task)
        found = await reader.get(run.id)
        assert found is not None and found.status == "ok"
        assert len(await reader.recent(RunFilter(), 10)) == 1
        assert (await reader.stats(0))[0]["count"] == 1
    finally:
        if not task.done():
            await writer.stop(task)
        await database.close()


@pytest.mark.anyio
async def test_saved_stale_progress_is_reported_lost() -> None:
    store = SlowStore()
    run = record("stale", status="running")
    run.updated_at = time.time() - LOST_AFTER_SECONDS - 1
    await store.save([run])
    reader = Recorder(store)
    assert (await reader.get("stale")).status == "lost"


@pytest.mark.anyio
async def test_failure_only_policy_does_not_write_success_progress() -> None:
    from shared.records.models import RunRecord
    from shared.records.recorder import Recorder
    from shared.records.stores import MemoryRunStore

    store = MemoryRunStore(10)
    recorder = Recorder(store)
    success = RunRecord("r", "r", "", "", "c", "t", "m", "1", "dev", "", "", "x", 0)
    recorder.start(success, record_success=False)
    await recorder.save_progress()
    assert not store.rows
    success.status = "ok"
    await recorder.finish(success)
    assert not store.rows and not recorder.failure_only
    failure = RunRecord("f", "f", "", "", "c", "t", "m", "1", "dev", "", "", "x", 0)
    recorder.start(failure, record_success=False)
    failure.status = "failed"
    await recorder.finish(failure)
    assert list(store.rows) == ["f"] and not recorder.failure_only
