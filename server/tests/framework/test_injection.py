import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.setup.build import Services, build
from shared.access.caller import DEVELOPER, PUBLIC
from shared.errors.framework import StepRuleBroken
from shared.jobs.views import count_jobs, get_job
from shared.model_calls.providers import FakeModel
from shared.public import (
    BusinessError,
    Call,
    Caller,
    Data,
    Db,
    Emitter,
    Flow,
    JobPlan,
    Kind,
    Later,
    Module,
    ModuleCache,
    Nothing,
    WorkData,
    contract,
    meaning,
    step,
)
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


class Order(Data):
    fail: bool = meaning("登记任务后是否故意失败", default=False)


class Receipt(Data):
    job_id: str = meaning("登记的任务编号")
    who: str = meaning("调用者编号")
    seen: bool = meaning("缓存中是否已有记录")


class OrderWork(WorkData):
    fail: bool = meaning("登记任务后是否故意失败")
    who: str = meaning("调用者编号")
    seen: bool = meaning("缓存中是否已有记录")
    job_id: str = meaning("登记的任务编号")
    result: Receipt = meaning("结果")


class NoteWork(WorkData):
    result: Nothing = meaning("没有返回内容")


class ProbeFailed(BusinessError):
    code = "probe_failed"
    kind = Kind.CONFLICT
    message = "按测试要求在登记任务后失败"


follow = contract(
    "inject_probe.follow",
    "后续任务",
    input=Nothing,
    output=Nothing,
    access=PUBLIC,
    effect="command",
)
order = contract(
    "inject_probe.order",
    "下单",
    input=Order,
    output=Receipt,
    access=PUBLIC,
    errors=(ProbeFailed,),
    effect="command",
)
talk = contract(
    "inject_probe.talk",
    "流式输出",
    input=Nothing,
    output=Nothing,
    access=PUBLIC,
    stream=True,
    effect="command",
)
twice = contract(
    "inject_probe.twice", "并发调用", input=Nothing, output=Nothing, access=PUBLIC, effect="command"
)
old = contract(
    "inject_probe.old", "读旧库", input=Nothing, output=Nothing, access=PUBLIC, effect="command"
)


@step("记下调用者", writes=["who"])
def note_caller(data: OrderWork, caller: Caller) -> None:
    data.who = caller.id


@step("查缓存", reads=["who"], writes=["seen"])
async def check_seen(data: OrderWork, cache: ModuleCache) -> None:
    data.seen = await cache.get_text(data.who) is not None
    await cache.set_text(data.who, "1", 60)


@step(
    "登记后续任务",
    reads=["fail", "who", "seen"],
    writes=["job_id", "result"],
    later=[follow],
    saves=True,
)
async def save_order(data: OrderWork, later: Later) -> None:
    data.job_id = await later(follow, Nothing())
    if data.fail:
        raise ProbeFailed()
    data.result = Receipt(job_id=data.job_id, who=data.who, seen=data.seen)


@step("完成", writes=["result"])
async def finish(data: NoteWork) -> None:
    await asyncio.sleep(0.01)
    data.result = Nothing()


@step("输出分段", writes=["result"])
async def emit_text(data: NoteWork, emit: Emitter) -> None:
    await emit("不应输出")
    data.result = Nothing()


@step("并发调用", writes=["result"], uses=[follow])
async def call_twice(data: NoteWork, call: Call) -> None:
    await asyncio.gather(call(follow, Nothing()), call(follow, Nothing()))
    data.result = Nothing()


class OldStore:
    def __init__(self, legacy: Db) -> None:
        self.legacy = legacy


@step("读旧库", writes=["result"])
async def read_old(data: NoteWork, store: OldStore) -> None:
    data.result = Nothing()


probe = Module(
    "inject_probe",
    "注入测试",
    "1",
    {
        order: Flow(
            "下单", work=OrderWork, result="result", steps=[note_caller, check_seen, save_order]
        ),
        follow: Flow("后续任务", work=NoteWork, result="result", steps=[finish]),
        talk: Flow("流式输出", work=NoteWork, result="result", steps=[emit_text]),
        twice: Flow("并发调用", work=NoteWork, result="result", steps=[call_twice]),
        old: Flow("读旧库", work=NoteWork, result="result", steps=[read_old]),
    },
    store=OldStore,
    jobs=(JobPlan(follow),),
    kind="capability",
)


@pytest.fixture
async def services(tmp_path: Path) -> AsyncIterator[Services]:
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    built = build(settings, modules=[probe], provider=FakeModel())
    yield built
    await built.close()


async def test_later_caller_and_cache(services: Services) -> None:
    first = await services.runtime.run(order, Order(), caller=DEVELOPER)
    assert first.who == "developer" and not first.seen
    job = await get_job(services.database, first.job_id)
    assert job is not None and job.contract == "inject_probe.follow"
    second = await services.runtime.run(order, Order(), caller=DEVELOPER)
    assert second.seen


async def test_later_rolls_back_with_business(services: Services) -> None:
    before = await count_jobs(services.database)
    with pytest.raises(ProbeFailed):
        await services.runtime.run(order, Order(fail=True), caller=DEVELOPER)
    assert await count_jobs(services.database) == before


async def test_tool_misuse_is_reported(services: Services) -> None:
    with pytest.raises(StepRuleBroken, match="没有以流式接口执行"):
        await services.runtime.run(talk, Nothing(), caller=DEVELOPER)
    with pytest.raises(StepRuleBroken, match="逐个 await"):
        await services.runtime.run(twice, Nothing(), caller=DEVELOPER)
    with pytest.raises(StepRuleBroken, match="APP_LEGACY_DATABASE_URL"):
        await services.runtime.run(old, Nothing(), caller=DEVELOPER)
