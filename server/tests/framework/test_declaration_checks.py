from decimal import Decimal
from typing import Any

import pytest

from shared.errors.framework import DeclarationError
from shared.modules.catalog import Catalog
from shared.public import Data, Flow, Module, WorkData, condition, contract, meaning, step
from tests.framework.sample_modules import NoteStore, calc, calc_module


class Ask(Data):
    amount: Decimal = meaning("金额")


class Answer(Data):
    total: Decimal = meaning("应付")


class Work(WorkData):
    amount: Decimal = meaning("金额")
    rate: Decimal = meaning("折扣率")
    total: Decimal = meaning("应付")
    answer: Answer = meaning("结果")


@step("计算应付", reads=["amount"], writes=["total"])
def count_total(data: Work) -> None:
    data.total = data.amount


@step("整理结果", reads=["total"], writes=["answer"])
def build_answer(data: Work) -> None:
    data.answer = Answer(total=data.total)


ask = contract("check_demo.ask", "检查示例", input=Ask, output=Answer, access="check_demo.use")


def problems_of(*steps: Any, work: type[WorkData] = Work, **options: Any) -> list[str]:
    flow = Flow("检查示例", work=work, result="answer", steps=list(steps))
    module = Module("check_demo", "检查示例", "1", provides={ask: flow}, **options)
    with pytest.raises(DeclarationError) as caught:
        Catalog([module])
    return caught.value.problems


def test_valid_flow_passes() -> None:
    flow = Flow("检查示例", work=Work, result="answer", steps=[count_total, build_answer])
    Catalog([Module("check_demo", "检查示例", "1", provides={ask: flow})])


def test_read_before_write() -> None:
    problems = problems_of(build_answer, count_total)
    assert any("“整理结果”读取的字段 total 在它之前没有确定的值" in item for item in problems)


def test_unknown_fields() -> None:
    @step("坏步骤", reads=["price"], writes=["answer"])
    def read_price(data: Work) -> None: ...

    assert any("读取的字段 price 不在流程数据中" in item for item in problems_of(read_price))


def test_two_writers() -> None:
    @step("再算一次", reads=["amount"], writes=["total"])
    def count_again(data: Work) -> None: ...

    problems = problems_of(count_total, count_again, build_answer)
    assert any("字段 total 被“计算应付”、“再算一次”同时写入" in item for item in problems)


def test_overwrite_input() -> None:
    @step("改金额", reads=[], writes=["amount"])
    def change_amount(data: Work) -> None: ...

    assert any(
        "覆盖了输入字段 amount" in item
        for item in problems_of(change_amount, count_total, build_answer)
    )


def test_param_mismatch() -> None:
    @step("调用", reads=["amount"], writes=["total"])
    async def call_other(data: Work, call: Any) -> None: ...

    @step("读取", reads=["total"], writes=["answer"])
    async def read_answer(data: Work, store: Any) -> None: ...

    problems = problems_of(call_other, read_answer)
    assert any("参数 call 与声明 uses= 必须同时出现" in item for item in problems)
    assert any("使用了 store，但所在模块没有在 module.py 中声明 store" in item for item in problems)


def test_one_kind_per_step() -> None:
    @step("混合", reads=["amount"], writes=["total"], uses=[calc])
    async def mix_work(data: Work, store: Any, call: Any) -> None: ...

    problems = problems_of(mix_work, build_answer, store=NoteStore)
    assert any("一个步骤只做一类事" in item for item in problems)


def test_conditional_write_needs_default() -> None:
    @condition("金额大于零", reads=["amount"])
    def is_positive(data: Work) -> bool:
        return bool(data.amount > 0)

    @step("算折扣", reads=["amount"], writes=["rate"], when=is_positive)
    def count_rate(data: Work) -> None: ...

    @step("用折扣", reads=["rate"], writes=["total"])
    def apply_rate(data: Work) -> None: ...

    problems = problems_of(count_rate, apply_rate, build_answer)
    assert any("“用折扣”读取的字段 rate 在它之前没有确定的值" in item for item in problems)


def test_field_notes_required() -> None:
    class Loose(WorkData):
        amount: Decimal = meaning("金额")
        total: Decimal
        memo: str | None = meaning("备注")
        answer: Answer = meaning("结果")

    problems = problems_of(count_total, build_answer, work=Loose)
    assert any("Loose.total 没有用 meaning() 写中文含义" in item for item in problems)
    assert any("Loose.memo 允许为空，但没有用 empty= 说明" in item for item in problems)


def test_model_after_save_is_rejected() -> None:
    from tests.framework.sample_modules import SlowInput, TextResult, explain, save_mark

    @step("调用说明", reads=["mark"], writes=["text"], uses=[explain])
    async def ask_after(data: Any, call: Any) -> None: ...

    class LateWork(WorkData):
        seconds: float = meaning("等待秒数")
        mark: str = meaning("文字")
        saved: int = meaning("行数")
        result: Any = meaning("结果")
        text: TextResult = meaning("说明")

    late = contract(
        "late_demo.run", "后调模型", input=SlowInput, output=TextResult, access="late_demo.use"
    )
    flow = Flow("后调模型", work=LateWork, result="text", steps=[save_mark, ask_after])
    module = Module("late_demo", "后调模型", "1", provides={late: flow}, store=NoteStore)
    with pytest.raises(DeclarationError) as caught:
        Catalog([calc_module, module])
    assert any("在写入事务开始后" in item for item in caught.value.problems)


def test_too_many_steps() -> None:
    parts = []
    for index in range(13):

        @step(f"第{index}步", reads=[], writes=[])
        def do_nothing(data: Work) -> None: ...

        parts.append(do_nothing)
    assert any("超过 12 个" in item for item in problems_of(*parts))
