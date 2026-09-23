"""
并发测试，只在 PostgreSQL 上运行（SQLite 同一时间只允许一个写入者，测不出并发问题）：
多个 worker 同时领取时不会拿到同一个任务；多个请求同时登记时不会超过排队上限。
"""

import asyncio
import time

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.errors.framework import QueueFull
from tests.framework.sample_modules import CalcInput, SlowInput, calc, slow

pytestmark = [pytest.mark.anyio, pytest.mark.postgres_only]


# 十个任务被八个领取者同时抢，每个任务只被领取一次。
async def test_concurrent_claims_do_not_overlap(sample: Services) -> None:
    for amount in range(10):
        await sample.runtime.submit(calc, CalcInput(amount=amount), caller=DEVELOPER)
    rounds = [
        asyncio.gather(*(sample.queue.claim(time.time()) for _ in range(8))) for _ in range(2)
    ]
    tickets = [ticket for batch in rounds for ticket in await batch if ticket is not None]
    ids = [ticket.id for ticket in tickets]
    assert len(ids) == 10 and len(set(ids)) == 10


# 排队上限为 2、已有一个任务在执行时，六个请求同时登记只有一个成功。
async def test_concurrent_submits_respect_limit(sample: Services) -> None:
    await sample.runtime.submit(slow, SlowInput(mark="first"), caller=DEVELOPER)
    await sample.queue.claim(time.time())

    # 登记一个任务，排队已满时返回 None。
    async def try_submit(mark: str) -> str | None:
        try:
            return await sample.runtime.submit(slow, SlowInput(mark=mark), caller=DEVELOPER)
        except QueueFull:
            return None

    results = await asyncio.gather(*(try_submit(str(index)) for index in range(6)))
    assert sum(result is not None for result in results) == 1
