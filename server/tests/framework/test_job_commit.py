import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.jobs.views import get_job
from shared.records.stores import RunFilter
from tests.framework.sample_modules import SlowInput, slow
from tests.framework.test_jobs import make_worker
from tests.framework.test_runner import count_notes


@pytest.mark.anyio
async def test_takeover_after_precheck_rolls_back_old_commit(
    sample: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = await sample.runtime.submit(slow, SlowInput(mark="old"), caller=DEVELOPER)
    old = await sample.queue.claim(time.time())
    assert old is not None
    original = sample.runtime.run
    finish = AsyncMock(wraps=sample.queue.finish)
    monkeypatch.setattr(sample.queue, "finish", finish)

    async def run_after_takeover(*args: Any, **kwargs: Any) -> Any:
        later = time.time() + 1
        assert await sample.queue.reclaim(later) == 1
        new = await sample.queue.claim(later)
        assert new is not None and new.attempt == old.attempt + 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(sample.runtime, "run", run_after_takeover)
    worker = make_worker(sample)
    monkeypatch.setattr(worker, "keep_lease", AsyncMock(return_value=None))
    await worker.execute(old)
    assert finish.await_count == 1
    assert await count_notes(sample) == 0
    job = await get_job(sample.database, job_id)
    assert job is not None and job.state == "running" and job.attempt == 2
    records = await sample.recorder.recent(RunFilter(job_id=job_id), 10)
    assert any(record.writes == "rolled_back" for record in records)
