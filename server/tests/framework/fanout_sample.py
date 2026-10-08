"""
美团式独立框架样例：封存来源、登记200个采集成员、每成员提交和轮询、单独汇算。
"""

from sqlalchemy import Column, Integer, MetaData, PrimaryKeyConstraint, Table, func, insert, select

from shared.access.caller import Caller
from shared.db.org import org_column
from shared.pipelines.gate import PipelineGate
from shared.public import (
    All,
    Data,
    Db,
    FanOut,
    Flow,
    JobPlan,
    Member,
    Module,
    Pipeline,
    Stage,
    Wait,
    WorkData,
    contract,
    meaning,
    step,
)

sample_metadata = MetaData()
versions = Table(
    "fanout_sample_versions", sample_metadata, Column("version", Integer, primary_key=True)
)
collected = Table(
    "fanout_sample_collected",
    sample_metadata,
    Column("id", Integer),
    org_column(),
    PrimaryKeyConstraint("org_id", "id"),
    Column("version", Integer, nullable=False),
    Column("value", Integer, nullable=False),
)
polls = Table(
    "fanout_sample_polls",
    sample_metadata,
    Column("id", Integer),
    Column("version", Integer),
    org_column(),
)


# 只传本次要规划的数量。
class Begin(Data):
    count: int = meaning("成员数量", default=200)


# 第一阶段选定并固定的来源引用。
class Source(Data):
    count: int = meaning("成员数量")
    version: int = meaning("已选来源版本")


# 规划结果只传引用及数量，不塞入200份成员结果。
class Batch(Data):
    count: int = meaning("本批成员数量")


# 每个成员的稳定请求输入。
class Request(Data):
    id: int = meaning("成员请求编号")


# 提交和查询上游返回的小型结果引用。
class Result(Data):
    id: int = meaning("成员请求编号")
    version: int = meaning("固定来源版本")
    value: int = meaning("合成汇算值")
    ready: bool = meaning("上游就绪", default=False)


# 汇算最终结果。
class Total(Data):
    count: int = meaning("实际纳入成员数")
    value: int = meaning("汇算合计")
    versions: list[int] = meaning("实际消费的来源版本")


# 来源选择的操作数据。
class SourceWork(WorkData):
    count: int = meaning("成员数量")
    result: Source = meaning("固定来源")


# 成员规划操作数据。
class PlanWork(WorkData):
    count: int = meaning("成员数量")
    version: int = meaning("选定来源版本")
    result: Batch = meaning("成员批引用")


# 单个成员的采集数据。
class CollectWork(WorkData):
    id: int = meaning("成员编号")
    source: Source = meaning("本次固定来源")
    result: Result = meaning("采集结果引用")


# 单次轮询的数据。
class PollWork(WorkData):
    id: int = meaning("成员编号")
    version: int = meaning("固定来源版本")
    value: int = meaning("合成汇算值")
    ready: bool = meaning("上游就绪")
    result: Result = meaning("轮询结果")


# 汇总阶段的数据。
class SumWork(WorkData):
    count: int = meaning("规划数量")
    result: Total = meaning("最终合计")


# 用真实数据库记录采集与轮询，便于检查重复、遗漏和来源混入。
class Store:
    # 绑定框架事务，测试表不进入业务模板。
    def __init__(self, db: Db, caller: Caller) -> None:
        self.db, self.caller = db, caller

    # 第一阶段选择一次最新来源。
    async def select_version(self) -> int:
        return int(await self.db.scalar(select(func.max(versions.c.version))))

    # 保存每个成员唯一结果；重复写入会触发真实主键约束。
    async def collect(self, id: int, version: int) -> Result:
        await self.db.change(
            insert(collected).values(
                id=id, version=version, value=id * version, org_id=self.caller.org_id
            )
        )
        return Result(id=id, version=version, value=id * version)

    # 模拟第二次查询时上游就绪，不在任务中sleep。
    async def poll(self, data: PollWork) -> Result:
        await self.db.change(
            insert(polls).values(id=data.id, version=data.version, org_id=self.caller.org_id)
        )
        count = await self.db.scalar(
            select(func.count()).where(polls.c.id == data.id, polls.c.org_id == self.caller.org_id)
        )
        return Result(id=data.id, version=data.version, value=data.value, ready=count >= 2)


# 选来源操作不承担200个成员的协调。
@step("选来源", reads=["count"], writes=["result"])
async def select_source(data: SourceWork, store: Store) -> None:
    data.result = Source(count=data.count, version=await store.select_version())


# 成员只做业务输入规划，派发和恢复均由框架完成。
@step("登记成员", reads=["count", "version"], writes=["result"], saves=True)
async def plan_members(data: PlanWork, pipeline: PipelineGate) -> None:
    await pipeline.add_members(
        [Member[Request](key=f"{id:04}", input=Request(id=id)) for id in range(1, data.count + 1)]
    )
    data.result = Batch(count=data.count)


# 从声明的来源获取固定版本，后来的新版本不会参与。
@step("读取固定来源", reads=[], writes=["source"])
async def read_source(data: CollectWork, pipeline: PipelineGate) -> None:
    data.source = await pipeline.source(Source)


# 采集的外部效果由独立样例SQL替代，真实业务仍通过已登记公开操作。
@step("保存采集结果", reads=["id", "source"], writes=["result"], saves=True)
async def collect_member(data: CollectWork, store: Store) -> None:
    data.result = await store.collect(data.id, data.source.version)


# 单个成员一次轮询，等待间隔由Wait声明负责。
@step("查询成员结果", reads=["id", "version", "value", "ready"], writes=["result"], saves=True)
async def poll_member(data: PollWork, store: Store) -> None:
    data.result = await store.poll(data)


# 读取冻结纳入结果的有界Data页，然后单独汇算。
@step("成员汇算", reads=["count"], writes=["result"])
async def sum_members(data: SumWork, pipeline: PipelineGate) -> None:
    count = value = 0
    source_versions = set()
    after = ""
    while True:
        page = await pipeline.results("requests", Result, after=after, limit=50)
        count += len(page.items)
        value += sum(item.result.value for item in page.items)
        source_versions.update(item.result.version for item in page.items)
        if not page.next_after:
            break
        after = page.next_after
    data.result = Total(count=count, value=value, versions=sorted(source_versions))


choose = contract(
    "fanout_sample.choose", "选来源", input=Begin, output=Source, access="fanout_sample.run"
)
plan = contract(
    "fanout_sample.plan", "规划成员", input=Source, output=Batch, access="fanout_sample.run"
)
collect = contract(
    "fanout_sample.collect", "采集成员", input=Request, output=Result, access="fanout_sample.run"
)
poll = contract(
    "fanout_sample.poll", "检查成员", input=Result, output=Result, access="fanout_sample.run"
)
combine = contract(
    "fanout_sample.combine", "单独汇算", input=Batch, output=Total, access="fanout_sample.run"
)
pipeline = Pipeline(
    "fanout_sample.daily",
    "200成员采集汇算",
    Begin,
    (
        Stage("choose", choose, freeze_sources=True),
        FanOut(
            "requests",
            plan,
            stages=(
                Stage("submit", collect, source=Source),
                Wait("ready", poll, every=0.001, timeout=20, max_parallel=3),
            ),
            join=All(),
            max_parallel=8,
        ),
        Stage("combine", combine, members={"requests": Result}),
    ),
)
module = Module(
    name="fanout_sample",
    title="200成员样例",
    version="1",
    store=Store,
    provides={
        choose: Flow("选来源", work=SourceWork, result="result", steps=[select_source]),
        plan: Flow("登记成员", work=PlanWork, result="result", steps=[plan_members]),
        collect: Flow(
            "采集成员", work=CollectWork, result="result", steps=[read_source, collect_member]
        ),
        poll: Flow("查询成员", work=PollWork, result="result", steps=[poll_member]),
        combine: Flow("单独汇算", work=SumWork, result="result", steps=[sum_members]),
    },
    jobs=tuple(
        JobPlan(op, repeat_safe=True, max_queued=3) for op in (choose, plan, collect, poll, combine)
    ),
    pipelines=(pipeline,),
)
