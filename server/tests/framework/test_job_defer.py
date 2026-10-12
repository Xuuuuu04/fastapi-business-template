"""
明确的冷却延后释放执行位置，不消耗失败重试次数，冷却后仍重新检查任务。
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.errors.framework import RemoteUnavailable
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.public import (
    ApplicationSpec,
    FakeClock,
    Flow,
    JobPlan,
    Module,
    Nothing,
    ResourceLimit,
    Retry,
    RetryLater,
    WorkData,
    contract,
    meaning,
    step,
)
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


# 每次只有一个明确的空结果，业务失败与延后分别发生。
class Work(WorkData):
    result: Nothing = meaning("完成结果")


# 合成两次429等待、一次暂时失败和一次成功，不把等待变成失败重试。
def deferred_module() -> Module:
    count = 0
    operation = contract(
        "defer_probe.run",
        "延后处理",
        input=Nothing,
        output=Nothing,
        access="public",
        effect="command",
    )

    # 前两次没有产生效果，只告诉框架何时重新核对。
    @step("尝试合成处理", writes=["result"])
    def work(data: Work) -> None:
        nonlocal count
        count += 1
        if count <= 2:
            raise RetryLater(10, resource="model", detail="合成429冷却")
        if count == 3:
            raise RemoteUnavailable("合成暂时失败")
        data.result = Nothing()

    return Module(
        "defer_probe",
        "延后处理",
        "1",
        {operation: Flow("合成处理", work=Work, result="result", steps=[work])},
        jobs=(JobPlan(operation, retry=Retry(1, (0,)), resources=(ResourceLimit("model"),)),),
        kind="capability",
    )


# 明确等待两次后仍有一次失败重试额度，所有等待期间都没有资源位置。
async def test_deferred_attempts_do_not_consume_retry_budget(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    clock, module = FakeClock(100), deferred_module()
    operation = next(iter(module.provides))
    services = build(settings, modules=[module], application=ApplicationSpec(clock=clock))
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    try:
        id = await services.runtime.submit(operation, Nothing(), caller=SYSTEM)
        for index in range(4):
            ticket = await services.queue.claim(clock.now())
            assert ticket is not None
            await worker.execute(ticket)
            if index < 2:
                assert await services.queue.claim(clock.now()) is None
                clock.advance(10)
        async with services.database.read() as connection:
            row = (await connection.execute(select(jobs).where(jobs.c.id == id))).mappings().one()
        assert row["state"] == "done" and row["attempt"] == 4 and row["failed_attempts"] == 1
    finally:
        await services.close()
