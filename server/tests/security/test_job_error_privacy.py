import logging
import time
from dataclasses import replace
from decimal import Decimal

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.jobs.views import get_job
from tests.framework.sample_modules import CalcInput, calc
from tests.framework.test_jobs import make_worker

pytestmark = pytest.mark.anyio


async def test_invalid_job_input_is_not_in_error(sample: Services) -> None:
    job_id = await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    ticket = await sample.queue.claim(time.time())
    assert ticket is not None
    marker = "synthetic_private_job_value"
    await make_worker(sample).execute(replace(ticket, input_json='{"amount":"' + marker + '"}'))
    job = await get_job(sample.database, job_id)
    assert job is not None and job.error_code == "input_invalid"
    assert marker not in job.error_message and "当前格式" in job.error_message


async def test_job_exception_preserves_only_safe_details(
    sample: Services, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    job_id = await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=DEVELOPER)
    ticket = await sample.queue.claim(time.time())
    assert ticket is not None
    marker = "synthetic_private_job_exception"

    async def failed(*args: object, **kwargs: object) -> None:
        error = ValueError(marker)
        error.run_id = "synthetic-run-id"
        raise error

    monkeypatch.setattr(sample.runtime, "run", failed)
    logger = logging.getLogger("server.jobs")
    logger.addHandler(caplog.handler)
    try:
        await make_worker(sample).execute(ticket)
        job = await get_job(sample.database, job_id)
        assert job is not None and job.error_code == "ValueError"
        assert job.last_run_id == "synthetic-run-id" and marker not in job.error_message
        assert marker not in caplog.text and "ValueError" in caplog.text
    finally:
        logger.removeHandler(caplog.handler)
