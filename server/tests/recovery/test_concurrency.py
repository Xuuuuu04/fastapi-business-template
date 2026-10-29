import asyncio
import time

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.errors.framework import QueueFull
from tests.framework.sample_modules import CalcInput, SlowInput, calc, slow

pytestmark = [pytest.mark.anyio, pytest.mark.postgres_only]


async def test_concurrent_claims_do_not_overlap(sample: Services) -> None:
    for amount in range(10):
        await sample.runtime.submit(calc, CalcInput(amount=amount), caller=DEVELOPER)
    rounds = [
        asyncio.gather(*(sample.queue.claim(time.time()) for _ in range(8))) for _ in range(2)
    ]
    tickets = [ticket for batch in rounds for ticket in await batch if ticket is not None]
    ids = [ticket.id for ticket in tickets]
    assert len(ids) == 10 and len(set(ids)) == 10


async def test_concurrent_submits_respect_limit(sample: Services) -> None:
    await sample.runtime.submit(slow, SlowInput(mark="first"), caller=DEVELOPER)
    await sample.queue.claim(time.time())

    async def try_submit(mark: str) -> str | None:
        try:
            return await sample.runtime.submit(slow, SlowInput(mark=mark), caller=DEVELOPER)
        except QueueFull:
            return None

    results = await asyncio.gather(*(try_submit(str(index)) for index in range(6)))
    assert sum(result is not None for result in results) == 1
