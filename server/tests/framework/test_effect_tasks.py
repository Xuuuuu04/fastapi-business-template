"""
业务提交后发送、回滚后不发送与统一运行记录，使用真实事务和持久队列合成验证。
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.effects.module import dispatch
from shared.effects.spec import EffectAdapter, ProviderSpec
from shared.effects.tables import intents
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.public import (
    ApplicationSpec,
    EffectGate,
    Flow,
    Module,
    Nothing,
    WorkData,
    contract,
    meaning,
    step,
)
from tests.framework.test_provider_effects import Adapter, Input, Output
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio

provider = ProviderSpec("messages.send", "合成消息", Input, Output, "smtp")
write = contract(
    "message_queue.write",
    "随业务发送",
    input=Input,
    output=Nothing,
    access="public",
    effect="command",
)


# 正文只在调用范围使用，意图与任务分开保存。
class Work(WorkData):
    message: str = meaning("合成消息")
    result: Nothing = meaning("登记结果")


# 不调用网络，意图与任务一起随业务事务提交。
@step("登记外部任务", reads=["message"], writes=["result"], saves=True, providers=[provider])
async def enqueue(data: Work, effects: EffectGate) -> None:
    await effects.enqueue(provider, Input(message=data.message), key="business-1")
    data.result = Nothing()


# 最后一步失败，之前登记的两种持久数据必须一起撤销。
@step("模拟后续失败")
def fail(data: Work) -> None:
    raise ValueError("合成业务失败")


# 构造临时声明，不把真实产品或合成业务登记到空模板。
def module_for(*, failing: bool) -> Module:
    return Module(
        "message_queue",
        "发送业务",
        "1",
        {
            write: Flow(
                "随业务发送",
                work=Work,
                result="result",
                steps=[enqueue, *([fail] if failing else [])],
            )
        },
        providers=(provider,),
        kind="workflow",
    )


# 提交只保存，worker通过同一产品组装实际调用，回滚后worker无任务可领。
@pytest.mark.parametrize("failing", [False, True])
async def test_effect_task_is_atomic_with_business(tmp_path: Path, failing: bool) -> None:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    adapter = Adapter()
    bindings: dict[ProviderSpec, EffectAdapter] = {provider: adapter}
    services = build(
        settings,
        modules=[module_for(failing=failing)],
        application=ApplicationSpec(providers=(provider,)),
        effect_adapters=bindings,
    )
    try:
        if failing:
            with pytest.raises(ValueError):
                await services.runtime.run(write, Input(message="private-body"), caller=SYSTEM)
        else:
            await services.runtime.run(write, Input(message="private-body"), caller=SYSTEM)
        assert adapter.sent == 0
        async with services.database.read() as connection:
            rows = (await connection.execute(select(intents))).mappings().all()
            tasks = (await connection.execute(select(jobs))).mappings().all()
        assert len(rows) == len(tasks) == (0 if failing else 1)
        if not failing:
            assert "private-body" not in tasks[0]["input_json"]
            ticket = await services.queue.claim(10**12)
            assert ticket is not None and ticket.contract == dispatch.name
            worker = Worker(services.runtime, services.queue, [], WorkerOptions())
            await worker.execute(ticket)
            assert adapter.sent == 1
            async with services.database.read() as connection:
                state = (await connection.execute(select(intents.c.state))).scalar_one()
            assert state == "accepted"
    finally:
        await services.close()
