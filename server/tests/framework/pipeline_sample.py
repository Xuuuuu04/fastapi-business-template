"""
四阶段独立流程样例：选择、采集、短时轮询、发布；只在框架测试中登记。
"""

from datetime import timedelta

from sqlalchemy import Column, Integer, MetaData, String, Table, func, insert, select

from shared.pipelines.plan import StartRequest
from shared.public import (
    Data,
    Db,
    Flow,
    JobPlan,
    Module,
    Pipeline,
    Schedule,
    Stage,
    Wait,
    WorkData,
    contract,
    meaning,
    step,
)

sample_metadata = MetaData()
events = Table(
    "sample_pipeline_events",
    sample_metadata,
    Column("id", Integer, primary_key=True),
    Column("mark", String(64)),
)


# 每阶段只传来源引用和是否就绪，不传大结果。
class Ref(Data):
    reference: str = meaning("固定来源引用", default="version-1")
    ready: bool = meaning("外部结果就绪", default=False)


# 阶段共享的数据。
class RefWork(WorkData):
    reference: str = meaning("固定来源引用")
    ready: bool = meaning("外部结果就绪")
    result: Ref = meaning("下一阶段输入")


# 记录实际阶段执行次数，用来证明恢复不会重做前序阶段。
class Store:
    # 绑定执行器提供的数据库访问。
    def __init__(self, db: Db) -> None:
        self.db = db

    # 记下阶段，等待第二次检查才返回就绪。
    async def record(self, name: str, reference: str) -> Ref:
        await self.db.change(insert(events).values(mark=name))
        count = await self.db.scalar(select(func.count()).where(events.c.mark == name))
        return Ref(reference=reference, ready=name != "wait" or count >= 2)


# 来源选择阶段。
@step("选来源", reads=["reference"], writes=["result"], saves=True)
async def choose(data: RefWork, store: Store) -> None:
    data.result = await store.record("choose", data.reference)


# 采集阶段。
@step("采集", reads=["reference"], writes=["result"], saves=True)
async def collect(data: RefWork, store: Store) -> None:
    data.result = await store.record("collect", data.reference)


# 一次等待检查，无循环与sleep。
@step("检查上游", reads=["reference"], writes=["result"], saves=True)
async def poll(data: RefWork, store: Store) -> None:
    data.result = await store.record("wait", data.reference)


# 发布阶段。
@step("发布", reads=["reference"], writes=["result"], saves=True)
async def publish(data: RefWork, store: Store) -> None:
    data.result = await store.record("publish", data.reference)


operations = tuple(
    contract(f"pipeline_sample.{name}", name, input=Ref, output=Ref, access="pipeline_sample.run")
    for name in ("choose", "collect", "poll", "publish")
)
pipeline = Pipeline(
    "pipeline_sample.daily",
    "四阶段日报",
    Ref,
    (
        Stage("choose", operations[0]),
        Stage("collect", operations[1]),
        Wait("wait", operations[2], every=0.001, timeout=10),
        Stage("publish", operations[3]),
    ),
)
module = Module(
    name="pipeline_sample",
    title="流程样例",
    version="1",
    store=Store,
    provides={
        op: Flow(op.title, work=RefWork, result="result", steps=[part])
        for op, part in zip(operations, (choose, collect, poll, publish), strict=True)
    },
    jobs=tuple(JobPlan(op, repeat_safe=True) for op in operations),
    pipelines=(pipeline,),
    schedules=(
        Schedule(
            "daily",
            "定时入口",
            pipeline.start,
            pipeline.start.input(request=StartRequest[Ref](data=Ref())),
            every=timedelta(minutes=1),
            org_ids=("org-a",),
            slot_input_field="request.period",
        ),
    ),
)
