from decimal import Decimal
from typing import Any, cast

import pytest

from app.setup.build import build
from shared.access.caller import DEVELOPER
from shared.config.settings import Settings
from shared.errors.framework import StepRuleBroken
from shared.flow.testing import try_step
from shared.model_calls.providers import FakeModel
from shared.public import Data, Flow, Module, WorkData, contract, meaning, step
from tests.framework.sample_modules import NoteStore, sample_metadata
from tests.testing_app import reset_database

pytestmark = pytest.mark.anyio


class Ask(Data):
    items: list[str] = meaning("项目")


class Answer(Data):
    count: int = meaning("数量")


class Work(WorkData):
    items: list[str] = meaning("项目")
    total: Decimal = meaning("合计", unit="元")
    answer: Answer = meaning("结果")


@step("偷看合计", reads=["items"], writes=["total"])
def peek_total(data: Work) -> None:
    data.total = data.answer.count


@step("多写结果", reads=["items"], writes=["total"])
def write_extra(data: Work) -> None:
    data.total = Decimal("1")
    data.answer = Answer(count=1)


@step("写浮点数", reads=["items"], writes=["total"])
def write_float(data: Work) -> None:
    data.total = cast(Any, 1.5)


@step("忘记写入", reads=["items"], writes=["total"])
def forget_write(data: Work) -> None:
    return None


@step("计算合计", reads=["items"], writes=["total"])
def count_items(data: Work) -> None:
    data.total = Decimal(len(data.items))


def test_undeclared_read() -> None:
    with pytest.raises(StepRuleBroken, match="“偷看合计”读取了未声明的字段 answer（结果）"):
        try_step(peek_total, Work, items=["a"])


def test_undeclared_write() -> None:
    with pytest.raises(StepRuleBroken, match="写入了未声明的字段 answer"):
        try_step(write_extra, Work, items=["a"])


def test_strict_types() -> None:
    with pytest.raises(StepRuleBroken, match="total（合计） 的值类型不对：期望 Decimal"):
        try_step(write_float, Work, items=["a"])


def test_missing_write() -> None:
    with pytest.raises(StepRuleBroken, match="声明会写入"):
        try_step(forget_write, Work, items=["a"])


def test_try_step_returns_values() -> None:
    assert try_step(count_items, Work, items=["a", "b"]).values == {"total": Decimal(2)}


async def run_with(settings: Settings, *parts: Any) -> BaseException:
    ask = contract("rule_demo.run", "规则示例", input=Ask, output=Answer, access="rule_demo.use")
    flow = Flow("规则示例", work=Work, result="answer", steps=list(parts))
    module = Module("rule_demo", "规则示例", "1", provides={ask: flow}, store=NoteStore)
    await reset_database(settings.database_url)
    services = build(settings, modules=[module], provider=FakeModel())
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.create_all)
    try:
        with pytest.raises(StepRuleBroken) as caught:
            await services.runtime.run(ask, Ask(items=["a"]), caller=DEVELOPER)
        return caught.value
    finally:
        await services.close()


@step("整理结果", reads=["total"], writes=["answer"])
def build_answer(data: Work) -> None:
    data.answer = Answer(count=int(data.total))


async def test_step_must_not_return(settings: Settings) -> None:
    @step("返回合计", reads=["items"], writes=["total"])
    def return_total(data: Work) -> int:
        data.total = Decimal(0)
        return len(data.items)

    error = await run_with(settings, return_total, build_answer)
    assert "不要 return" in error.detail


async def test_in_place_change_is_found(settings: Settings) -> None:
    @step("偷改项目", reads=["items"], writes=["total"])
    def append_item(data: Work) -> None:
        data.items.append("x")
        data.total = Decimal(0)

    error = await run_with(settings, append_item, build_answer)
    assert "原地修改了只读字段 items" in error.detail


async def test_read_step_cannot_write(settings: Settings) -> None:
    @step("偷偷写入", reads=["items"], writes=["total"])
    async def sneak_write(data: Work, store: NoteStore) -> None:
        await store.add("x")
        data.total = Decimal(0)

    error = await run_with(settings, sneak_write, build_answer)
    assert "没有声明 saves=True，不能写入数据库" in error.detail
