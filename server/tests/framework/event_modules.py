"""
框架测试用的事件示例：sample_order 保存一行后发布“已下单”，sample_audit 订阅它并再记一行。
两个模块之间没有调用关系，只通过事件连接。表与 sample_modules 共用。
"""

from shared.public import (
    Data,
    Flow,
    Module,
    Publish,
    WorkData,
    contract,
    event,
    meaning,
    on,
    step,
)
from tests.framework.sample_modules import NoteStore


class OrderInput(Data):
    text: str = meaning("下单说明")
    fail: bool = meaning("发布后是否故意失败，测试用", default=False)


class OrderPlaced(Data):
    text: str = meaning("下单说明")


class Counted(Data):
    total: int = meaning("当前总行数")


class OrderWork(WorkData):
    text: str = meaning("下单说明")
    fail: bool = meaning("是否故意失败")
    result: Counted = meaning("结果")


order_placed = event("sample_order.placed", "已下单", data=OrderPlaced)


# 保存一行并发布“已下单”，按需要在发布后故意失败。
@step(
    "保存并发布",
    reads=["text", "fail"],
    writes=["result"],
    publishes=[order_placed],
    saves=True,
)
async def save_and_publish(data: OrderWork, store: NoteStore, publish: Publish) -> None:
    total = await store.add(data.text)
    await publish(order_placed, OrderPlaced(text=data.text))
    if data.fail:
        raise ValueError("故意在发布后失败")
    data.result = Counted(total=total)


place = contract(
    "sample_order.place", "下单", input=OrderInput, output=Counted, access="sample_order.use"
)
order_module = Module(
    name="sample_order",
    title="事件发布示例",
    version="1",
    provides={place: Flow("下单", work=OrderWork, result="result", steps=[save_and_publish])},
    store=NoteStore,
    publishes=(order_placed,),
)


class AuditWork(WorkData):
    text: str = meaning("下单说明")
    result: Counted = meaning("结果")


# 收到“已下单”后记一行。
@step("记录下单", reads=["text"], writes=["result"], saves=True)
async def record_order(data: AuditWork, store: NoteStore) -> None:
    data.result = Counted(total=await store.add(f"审计：{data.text}"))


record = contract(
    "sample_audit.record",
    "记录下单",
    input=OrderPlaced,
    output=Counted,
    access="sample_audit.write",
)
audit_module = Module(
    name="sample_audit",
    title="事件订阅示例",
    version="1",
    provides={record: Flow("记录下单", work=AuditWork, result="result", steps=[record_order])},
    store=NoteStore,
    subscribes=(on(order_placed, record),),
)
