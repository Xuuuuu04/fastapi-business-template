import asyncio
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, func, insert, select

from shared.public import (
    BusinessError,
    Call,
    Data,
    Db,
    Flow,
    JobPlan,
    Kind,
    Model,
    Module,
    Note,
    Retry,
    WorkData,
    condition,
    contract,
    meaning,
    prompt,
    step,
)

sample_metadata = MetaData()
notes = Table(
    "sample_calc_notes",
    sample_metadata,
    Column("id", Integer, primary_key=True),
    Column("text", String(40)),
)


class NoteStore:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def add(self, text: str) -> int:
        await self.db.change(insert(notes).values(text=text))
        return int(await self.db.scalar(select(func.count()).select_from(notes)))

    async def count(self) -> int:
        return int(await self.db.scalar(select(func.count()).select_from(notes)))


class SampleBusy(BusinessError):
    code = "sample_busy"
    kind = Kind.TEMPORARY
    message = "示例的暂时故障"


class CalcInput(Data):
    amount: Decimal = meaning("金额", unit="元")
    vip: bool = meaning("是否会员", default=False)
    fail_at: str = meaning("在哪一步故意失败，测试用", default="")


class CalcResult(Data):
    total: Decimal = meaning("应付", unit="元")
    saved: int = meaning("保存后的总行数")


class CalcWork(WorkData):
    amount: Decimal = meaning("金额", unit="元")
    vip: bool = meaning("是否会员")
    fail_at: str = meaning("故意失败的位置")
    discount: Decimal = meaning("优惠", unit="元", default=Decimal("0"))
    total: Decimal = meaning("应付", unit="元", log_value=True)
    saved: int = meaning("保存后的总行数")
    result: CalcResult = meaning("结果")


@condition("是会员", reads=["vip"])
def is_vip(data: CalcWork) -> bool:
    return data.vip


@step("计算优惠", reads=["amount"], writes=["discount"], when=is_vip)
def count_discount(data: CalcWork) -> None:
    data.discount = data.amount * Decimal("0.1")


@step("计算应付", reads=["amount", "discount", "fail_at"], writes=["total"])
def count_total(data: CalcWork, note: Note) -> None:
    if data.fail_at == "total":
        raise ValueError("故意在计算时失败")
    if data.fail_at == "busy":
        raise SampleBusy()
    data.total = data.amount - data.discount
    note("计算完成")


@step("保存结果", reads=["total", "fail_at"], writes=["saved"], saves=True)
async def save_total(data: CalcWork, store: NoteStore) -> None:
    data.saved = await store.add(str(data.total))
    if data.fail_at == "save":
        raise ValueError("故意在保存后失败")


@step("整理结果", reads=["total", "saved"], writes=["result"])
def build_result(data: CalcWork) -> None:
    data.result = CalcResult(total=data.total, saved=data.saved)


calc = contract(
    "sample_calc.calc",
    "示例计算",
    input=CalcInput,
    output=CalcResult,
    access="sample_calc.use",
    effect="command",
)
calc_flow = Flow(
    "示例计算",
    work=CalcWork,
    result="result",
    steps=[count_discount, count_total, save_total, build_result],
)


class SlowInput(Data):
    seconds: float = meaning("等待秒数", default=0.0)
    mark: str = meaning("要记下的文字")


class SlowResult(Data):
    saved: int = meaning("保存后的总行数")


class SlowWork(WorkData):
    seconds: float = meaning("等待秒数")
    mark: str = meaning("要记下的文字")
    saved: int = meaning("保存后的总行数")
    result: SlowResult = meaning("结果")


@step("等待", reads=["seconds"], writes=[])
async def wait_some(data: SlowWork) -> None:
    await asyncio.sleep(data.seconds)


@step("记下文字", reads=["mark"], writes=["saved", "result"], saves=True)
async def save_mark(data: SlowWork, store: NoteStore) -> None:
    data.saved = await store.add(data.mark)
    data.result = SlowResult(saved=data.saved)


slow = contract(
    "sample_calc.slow",
    "慢任务",
    input=SlowInput,
    output=SlowResult,
    access="sample_calc.use",
    effect="command",
)
slow_flow = Flow("慢任务", work=SlowWork, result="result", steps=[wait_some, save_mark])
hurried = contract(
    "sample_calc.hurried",
    "限时慢任务",
    input=SlowInput,
    output=SlowResult,
    access="sample_calc.use",
    timeout=0.05,
    effect="command",
)


class TextInput(Data):
    mark: str = meaning("要说明的文字")


class TextResult(Data):
    text: str = meaning("大模型写的说明")


class TextWork(WorkData):
    mark: str = meaning("要说明的文字")
    result: TextResult = meaning("结果")


describe = prompt(
    "describe_mark", "说明文字", file=Path(__file__).parent / "prompts" / "describe.md", version="3"
)


@step("请大模型说明", reads=["mark"], writes=["result"], prompts=[describe])
async def ask_text(data: TextWork, model: Model) -> None:
    data.result = TextResult(text=await model.ask(describe, mark=data.mark))


explain = contract(
    "sample_calc.explain",
    "说明文字",
    input=TextInput,
    output=TextResult,
    access="sample_calc.use",
    effect="command",
)
explain_flow = Flow("说明文字", work=TextWork, result="result", steps=[ask_text])

calc_module = Module(
    name="sample_calc",
    title="示例计算",
    version="1",
    provides={calc: calc_flow, slow: slow_flow, hurried: slow_flow, explain: explain_flow},
    store=NoteStore,
    prompts=(describe,),
    jobs=(
        JobPlan(calc, retry=Retry(times=1, waits=(0.0,))),
        JobPlan(slow, repeat_safe=True, lease_seconds=0.3, max_queued=2),
    ),
    kind="capability",
)


class OuterWork(WorkData):
    amount: Decimal = meaning("金额", unit="元")
    vip: bool = meaning("是否会员")
    fail_at: str = meaning("故意失败的位置")
    first: int = meaning("外层保存后的总行数")
    result: CalcResult = meaning("结果")


@step("外层保存", reads=["amount"], writes=["first"], saves=True)
async def save_first(data: OuterWork, store: NoteStore) -> None:
    data.first = await store.add("外层")


@step("调用示例计算", reads=["amount", "vip", "fail_at"], writes=["result"], uses=[calc])
async def call_calc(data: OuterWork, call: Call) -> None:
    data.result = await call(
        calc, CalcInput(amount=data.amount, vip=data.vip, fail_at=data.fail_at)
    )


outer = contract(
    "sample_outer.run",
    "外层操作",
    input=CalcInput,
    output=CalcResult,
    access="sample_outer.use",
    effect="command",
)
outer_module = Module(
    name="sample_outer",
    title="外层示例",
    version="1",
    provides={
        outer: Flow("外层操作", work=OuterWork, result="result", steps=[save_first, call_calc])
    },
    store=NoteStore,
    kind="workflow",
)
