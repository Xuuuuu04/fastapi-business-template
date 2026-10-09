"""
原件回放独立模块：读取原始JSON、等待、按批解析十万行、汇算并发布CSV，正式模板不登记。
"""

import json
from datetime import timedelta

from sqlalchemy import Column, Integer, MetaData, Table, func, insert, select

from shared.pipelines.plan import StartRequest
from shared.public import (
    Checkpoint,
    Data,
    Db,
    Flow,
    JobPlan,
    Module,
    ModuleFiles,
    Pipeline,
    RemoteClient,
    Schedule,
    Stage,
    Wait,
    WorkData,
    contract,
    meaning,
    remote,
    step,
)

sample_metadata = MetaData()
parsed = Table(
    "drill_sample_parsed",
    sample_metadata,
    Column("id", Integer, primary_key=True),
    Column("value", Integer, nullable=False),
)
upstream = remote("recorded_upstream", "录制上游", retries=0)


# 初始规模只指定期望条数。
class Begin(Data):
    count: int = meaning("真实规模条数", default=100000)


# 只传原件引用，不把十万行正文塞进阶段Data。
class Original(Data):
    name: str = meaning("原件引用")
    count: int = meaning("期望条数")
    ready: bool = meaning("原件可读", default=False)


# 按批解析结束后的行数证据。
class Parsed(Data):
    rows: int = meaning("已经确认解析的条数")


# 汇算结果。
class Stats(Data):
    rows: int = meaning("实际汇算条数")
    total: int = meaning("实际汇算合计")


# 可读取的发布文件引用。
class Published(Data):
    name: str = meaning("发布文件引用")
    rows: int = meaning("发布的汇算条数")


# 解析游标格式进入Pipeline声明保护。
class Cursor(Data):
    after: int = meaning("已经提交解析条数", default=0)


# 采集操作数据。
class CollectWork(WorkData):
    count: int = meaning("期望规模")
    result: Original = meaning("原件引用")


# 等待及解析操作数据。
class ParseWork(WorkData):
    name: str = meaning("原件引用")
    count: int = meaning("期望规模")
    ready: bool = meaning("原件就绪")
    result: Parsed = meaning("已解析条数")


# 等待检查数据。
class WaitWork(WorkData):
    name: str = meaning("原件引用")
    count: int = meaning("期望规模")
    ready: bool = meaning("原件就绪")
    result: Original = meaning("查询结果")


# 汇算操作数据。
class SumWork(WorkData):
    rows: int = meaning("已解析条数")
    result: Stats = meaning("汇算结果")


# 发布操作数据。
class PublishWork(WorkData):
    rows: int = meaning("汇算条数")
    total: int = meaning("汇算合计")
    result: Published = meaning("发布文件")


# 存储仅通过声明工具访问SQL、原件和回放上游。
class Store:
    # 本地原件与框架事务入口。
    def __init__(self, db: Db, files: ModuleFiles, remote: RemoteClient) -> None:
        self.db, self.files, self.remote = db, files, remote

    # 原始字节直接保留，用同一解析实现读取。
    async def collect(self, count: int) -> Original:
        reply = await self.remote.get(upstream, "/original", params={"count": str(count)})
        saved = await self.files.save_bytes("original.json", reply.content)
        return Original(name=saved.key, count=count)

    # 只查询一次原件是否可读，等待由框架重新登记。
    async def ready(self, name: str) -> bool:
        return await self.files.exists(name)

    # 每批按游标解析原件并保存，真实主键约束证明不会重复。
    async def parse(self, name: str, start: int, count: int) -> int:
        raw = json.loads(await self.files.read(name, 256000000))
        rows = raw["rows"][start : min(start + 5000, count)]
        await self.db.change(insert(parsed).values(rows))
        return len(rows)

    # SQL实际计算汇总，不从输入规模猜结果。
    async def sum(self) -> Stats:
        row = await self.db.first(
            select(func.count().label("rows"), func.sum(parsed.c.value).label("total"))
        )
        assert row is not None
        return Stats(rows=row["rows"], total=row["total"])

    # 发布可直接解析的CSV文件，不写外部系统。
    async def publish(self, rows: int, total: int) -> Published:
        saved = await self.files.save_bytes("report.csv", f"rows,total\n{rows},{total}\n".encode())
        return Published(name=saved.key, rows=rows)


# 采集原件在事务之前，外部请求由框架记录。
@step("采集原件", reads=["count"], writes=["result"])
async def collect_original(data: CollectWork, store: Store) -> None:
    data.result = await store.collect(data.count)


# 单次等待检查。
@step("确认原件可读", reads=["name", "count"], writes=["result"])
async def check_ready(data: WaitWork, store: Store) -> None:
    data.result = Original(name=data.name, count=data.count, ready=await store.ready(data.name))


# 一次调用只解析一批，最后提交点才完成阶段。
@step("按批解析原件", reads=["name", "count"], writes=["result"], saves=True)
async def parse_batch(data: ParseWork, store: Store, checkpoint: Checkpoint) -> None:
    start = int(checkpoint.cursor.get("after", 0))
    count = await store.parse(data.name, start, data.count)
    end = start + count
    data.result = Parsed(rows=end)
    if end == data.count:
        checkpoint.finish(rows=count, cursor={"after": end})
    else:
        checkpoint.advance({"after": end}, rows=count)


# 单独汇算阶段。
@step("SQL汇算", reads=["rows"], writes=["result"])
async def sum_rows(data: SumWork, store: Store) -> None:
    data.result = await store.sum()


# 单独发布阶段。
@step("发布CSV", reads=["rows", "total"], writes=["result"])
async def publish_csv(data: PublishWork, store: Store) -> None:
    data.result = await store.publish(data.rows, data.total)


collect = contract(
    "drill_sample.collect", "原件采集", input=Begin, output=Original, access="drill_sample.run"
)
wait = contract(
    "drill_sample.wait", "等待原件", input=Original, output=Original, access="drill_sample.run"
)
parse = contract(
    "drill_sample.parse", "批量解析", input=Original, output=Parsed, access="drill_sample.run"
)
aggregate = contract(
    "drill_sample.sum", "汇算", input=Parsed, output=Stats, access="drill_sample.run"
)
publish = contract(
    "drill_sample.publish", "发布", input=Stats, output=Published, access="drill_sample.run"
)
pipeline = Pipeline(
    "drill_sample.daily",
    "十万行原件演练",
    Begin,
    (
        Stage("collect", collect),
        Wait("wait", wait, every=0.01, timeout=10),
        Stage("parse", parse),
        Stage("sum", aggregate),
        Stage("publish", publish),
    ),
)
module = Module(
    name="drill_sample",
    title="原件演练",
    version="1",
    store=Store,
    tables=(parsed,),
    remotes=(upstream,),
    provides={
        collect: Flow("采集", work=CollectWork, result="result", steps=[collect_original]),
        wait: Flow("等待", work=WaitWork, result="result", steps=[check_ready]),
        parse: Flow("解析", work=ParseWork, result="result", steps=[parse_batch]),
        aggregate: Flow("汇算", work=SumWork, result="result", steps=[sum_rows]),
        publish: Flow("发布", work=PublishWork, result="result", steps=[publish_csv]),
    },
    jobs=tuple(
        JobPlan(op, repeat_safe=True, segmented=op is parse, cursor=Cursor if op is parse else None)
        for op in (collect, wait, parse, aggregate, publish)
    ),
    pipelines=(pipeline,),
    schedules=(
        Schedule(
            "daily",
            "实际定时入口",
            pipeline.start,
            pipeline.start.input(request=StartRequest[Begin](data=Begin())),
            every=timedelta(minutes=1),
            slot_input_field="request.period",
        ),
    ),
)
