"""
框架测试用的小模块，不属于业务，只用来验证执行器、事务、任务和大模型入口。
表登记在单独的 sample_metadata 上，不进入正式迁移。
"""

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


# 测试用数据访问实现，保存文字并统计当前记录数。
class NoteStore:
    # 使用框架提供的数据库入口。
    def __init__(self, db: Db) -> None:
        self.db = db

    # 记下一行文字，返回当前总行数。
    async def add(self, text: str) -> int:
        await self.db.change(insert(notes).values(text=text))
        return int(await self.db.scalar(select(func.count()).select_from(notes)))

    # 返回当前总行数。
    async def count(self) -> int:
        return int(await self.db.scalar(select(func.count()).select_from(notes)))


# 表示“示例的暂时故障”的失败，由统一错误入口返回给调用方。
class SampleBusy(BusinessError):
    code = "sample_busy"
    kind = Kind.TEMPORARY
    message = "示例的暂时故障"


# 计算测试接收的金额、会员状态和故意失败位置。
class CalcInput(Data):
    amount: Decimal = meaning("金额", unit="元")
    vip: bool = meaning("是否会员", default=False)
    fail_at: str = meaning("在哪一步故意失败，测试用", default="")


# 计算测试返回的应付金额与已保存记录数。
class CalcResult(Data):
    total: Decimal = meaning("应付", unit="元")
    saved: int = meaning("保存后的总行数")


# 计算测试各步骤共享的金额、折扣与保存结果。
class CalcWork(WorkData):
    amount: Decimal = meaning("金额", unit="元")
    vip: bool = meaning("是否会员")
    fail_at: str = meaning("故意失败的位置")
    discount: Decimal = meaning("优惠", unit="元", default=Decimal("0"))
    total: Decimal = meaning("应付", unit="元", log_value=True)
    saved: int = meaning("保存后的总行数")
    result: CalcResult = meaning("结果")


# 判断是否会员。
@condition("是会员", reads=["vip"])
def is_vip(data: CalcWork) -> bool:
    return data.vip


# 会员优惠 10%。
@step("计算优惠", reads=["amount"], writes=["discount"], when=is_vip, rule="R-01")
def count_discount(data: CalcWork) -> None:
    data.discount = data.amount * Decimal("0.1")


# 计算应付，按需要故意失败。
@step("计算应付", reads=["amount", "discount", "fail_at"], writes=["total"], rule="R-02")
def count_total(data: CalcWork, note: Note) -> None:
    if data.fail_at == "total":
        raise ValueError("故意在计算时失败")
    if data.fail_at == "busy":
        raise SampleBusy()
    data.total = data.amount - data.discount
    note("计算完成")


# 保存一行，按需要在保存后故意失败。
@step("保存结果", reads=["total", "fail_at"], writes=["saved"], saves=True)
async def save_total(data: CalcWork, store: NoteStore) -> None:
    data.saved = await store.add(str(data.total))
    if data.fail_at == "save":
        raise ValueError("故意在保存后失败")


# 整理结果。
@step("整理结果", reads=["total", "saved"], writes=["result"])
def build_result(data: CalcWork) -> None:
    data.result = CalcResult(total=data.total, saved=data.saved)


calc = contract(
    "sample_calc.calc", "示例计算", input=CalcInput, output=CalcResult, access="sample_calc.use"
)
calc_flow = Flow(
    "示例计算",
    work=CalcWork,
    result="result",
    steps=[count_discount, count_total, save_total, build_result],
)


# 慢任务测试接收的等待时间和要保存的文字。
class SlowInput(Data):
    seconds: float = meaning("等待秒数", default=0.0)
    mark: str = meaning("要记下的文字")


# 慢任务测试返回的已保存记录数量。
class SlowResult(Data):
    saved: int = meaning("保存后的总行数")


# 慢任务测试各步骤共享的等待时间、文字和保存结果。
class SlowWork(WorkData):
    seconds: float = meaning("等待秒数")
    mark: str = meaning("要记下的文字")
    saved: int = meaning("保存后的总行数")
    result: SlowResult = meaning("结果")


# 等待一段时间，模拟耗时的外部处理。
@step("等待", reads=["seconds"], writes=[])
async def wait_some(data: SlowWork) -> None:
    await asyncio.sleep(data.seconds)


# 记下文字并整理结果。
@step("记下文字", reads=["mark"], writes=["saved", "result"], saves=True)
async def save_mark(data: SlowWork, store: NoteStore) -> None:
    data.saved = await store.add(data.mark)
    data.result = SlowResult(saved=data.saved)


slow = contract(
    "sample_calc.slow", "慢任务", input=SlowInput, output=SlowResult, access="sample_calc.use"
)
slow_flow = Flow("慢任务", work=SlowWork, result="result", steps=[wait_some, save_mark])
hurried = contract(
    "sample_calc.hurried",
    "限时慢任务",
    input=SlowInput,
    output=SlowResult,
    access="sample_calc.use",
    timeout=0.05,
)


# 大模型测试接收的待说明文字。
class TextInput(Data):
    mark: str = meaning("要说明的文字")


# 大模型测试返回的生成文字。
class TextResult(Data):
    text: str = meaning("大模型写的说明")


# 大模型测试各步骤共享的输入文字和生成结果。
class TextWork(WorkData):
    mark: str = meaning("要说明的文字")
    result: TextResult = meaning("结果")


describe = prompt(
    "describe_mark", "说明文字", file=Path(__file__).parent / "prompts" / "describe.md", version="3"
)


# 请大模型说明一段文字。
@step("请大模型说明", reads=["mark"], writes=["result"], prompts=[describe])
async def ask_text(data: TextWork, model: Model) -> None:
    data.result = TextResult(text=await model.ask(describe, mark=data.mark))


explain = contract(
    "sample_calc.explain", "说明文字", input=TextInput, output=TextResult, access="sample_calc.use"
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
)


# 模块互相调用测试中共享的输入与两次计算结果。
class OuterWork(WorkData):
    amount: Decimal = meaning("金额", unit="元")
    vip: bool = meaning("是否会员")
    fail_at: str = meaning("故意失败的位置")
    first: int = meaning("外层保存后的总行数")
    result: CalcResult = meaning("结果")


# 外层先保存一行。
@step("外层保存", reads=["amount"], writes=["first"], saves=True)
async def save_first(data: OuterWork, store: NoteStore) -> None:
    data.first = await store.add("外层")


# 再调用示例计算。
@step("调用示例计算", reads=["amount", "vip", "fail_at"], writes=["result"], uses=[calc])
async def call_calc(data: OuterWork, call: Call) -> None:
    data.result = await call(
        calc, CalcInput(amount=data.amount, vip=data.vip, fail_at=data.fail_at)
    )


outer = contract(
    "sample_outer.run", "外层操作", input=CalcInput, output=CalcResult, access="sample_outer.use"
)
outer_module = Module(
    name="sample_outer",
    title="外层示例",
    version="1",
    provides={
        outer: Flow("外层操作", work=OuterWork, result="result", steps=[save_first, call_calc])
    },
    store=NoteStore,
)
