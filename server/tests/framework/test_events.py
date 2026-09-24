"""
模块事件：发布与业务写入同一事务，业务失败时事件不发出；订阅方由 worker 以最小权限的
“事件”身份执行，组织范围沿用发布时的调用者；启动检查拦下错误的发布和订阅声明。
"""

import json
import time
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select

from app.setup.build import Services, build
from shared.access.caller import Caller
from shared.config.settings import Settings
from shared.errors.framework import DeclarationError
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.model_calls.providers import FakeModel
from shared.modules.catalog import Catalog
from shared.public import Data, Flow, Module, contract, meaning, on
from tests.conftest import create_sample_tables
from tests.framework.event_modules import (
    AuditWork,
    OrderInput,
    audit_module,
    order_module,
    order_placed,
    place,
    record,
    record_order,
)
from tests.testing_app import reset_database

CALLER = Caller("u1", "user", "下单人", frozenset({"sample_order.use"}), "north")


# 只启用两个事件示例模块的服务。
@pytest.fixture
async def events(settings: Settings) -> AsyncIterator[Services]:
    await reset_database(settings.database_url)
    built = build(settings, modules=[order_module, audit_module], provider=FakeModel())
    await create_sample_tables(built)
    try:
        yield built
    finally:
        await built.close()


# 读取任务表中的全部任务。
async def queued(services: Services) -> list[dict[str, object]]:
    async with services.database.read() as connection:
        rows = await connection.execute(select(jobs.c.contract, jobs.c.caller_json, jobs.c.state))
        return [dict(row._mapping) for row in rows]


# 发布后订阅方任务与业务写入一起提交；worker 以事件身份执行订阅方。
@pytest.mark.anyio
async def test_published_event_runs_subscriber(events: Services) -> None:
    result = await events.runtime.run(place, OrderInput(text="甲"), caller=CALLER)
    assert result.total == 1
    [job] = await queued(events)
    assert job["contract"] == "sample_audit.record"
    caller = json.loads(str(job["caller_json"]))
    assert caller["kind"] == "event" and caller["org_id"] == "north"
    assert caller["permissions"] == ["sample_audit.write"]
    worker = Worker(events.runtime, events.queue, events.settings.api_keys, WorkerOptions())
    ticket = await events.queue.claim(time.time())
    assert ticket is not None
    await worker.execute(ticket)
    assert [job["state"] for job in await queued(events)] == ["done"]


# 发布之后业务失败，整个事务回滚，事件没有发出。
@pytest.mark.anyio
async def test_rolled_back_run_publishes_nothing(events: Services) -> None:
    with pytest.raises(ValueError):
        await events.runtime.run(place, OrderInput(text="乙", fail=True), caller=CALLER)
    assert await queued(events) == []


class Other(Data):
    text: str = meaning("说明")


# 订阅没有人发布的事件、处理操作输入不是事件数据，启动检查都会报出。
def test_wrong_subscriptions_are_rejected() -> None:
    wrong = contract(
        "sample_audit.other", "别的", input=Other, output=Other, access="sample_audit.w"
    )
    module = Module(
        name="sample_audit",
        title="错误订阅",
        version="1",
        provides={
            record: Flow("记录下单", work=AuditWork, result="result", steps=[record_order]),
            wrong: Flow("记录下单", work=AuditWork, result="result", steps=[record_order]),
        },
        store=audit_module.store,
        subscribes=(on(order_placed, wrong),),
    )
    with pytest.raises(DeclarationError) as caught:
        Catalog([module])
    text = str(caught.value)
    assert "没有由任何已启用的模块发布" in text
    assert "处理操作输入必须是事件数据 OrderPlaced" in text
