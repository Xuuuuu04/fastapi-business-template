"""
分段提交的独立框架样例，每次操作处理一批，不登记到产品 MODULES，不进入产品数据库迁移。
输入表保持固定，输出以输入行号为唯一键，便于检查恢复时是否重复或遗漏。
"""

import asyncio
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, insert, select

from shared.public import (
    Checkpoint,
    Data,
    Db,
    Flow,
    JobPlan,
    Module,
    Retry,
    WorkData,
    contract,
    meaning,
    step,
)

sample_metadata = MetaData()
source = Table(
    "segment_sample_source",
    sample_metadata,
    Column("id", Integer, primary_key=True),
)
output = Table(
    "segment_sample_output",
    sample_metadata,
    Column("id", Integer, primary_key=True),
    Column("value", Integer, nullable=False),
)


# 固定输入范围与单批大小；pause 参数只用于真实强杀验收。
class BatchInput(Data):
    total: int = meaning("固定输入总行数", default=100000)
    batch_size: int = meaning("每批处理行数", default=5000)
    pause_after: int = meaning("在此前已提交行数后暂停，负数表示不暂停", default=-1)
    signal_file: str = meaning("强杀验收的暂停信号文件", default="")


# 最后一批返回整个固定输入的已处理行数。
class BatchResult(Data):
    processed: int = meaning("累计处理行数")


# 每一批重新创建，仅恢复游标跨批保留。
class BatchWork(BatchInput, WorkData):
    start: int = meaning("上一个已提交的位置", default=0)
    end: int = meaning("本批结束位置", default=0)
    result: BatchResult = meaning("本批处理结果")


# 用独立测试表验证真实 SQL 写入和事务回滚。
class BatchStore:
    # 接收框架提供的事务入口。
    def __init__(self, db: Db) -> None:
        self.db = db

    # 只处理游标之后的一批，重复处理已提交行会触发唯一约束失败。
    async def save(self, start: int, end: int) -> int:
        statement = insert(output).from_select(
            ["id", "value"],
            select(source.c.id, source.c.id * 2).where(source.c.id > start, source.c.id <= end),
        )
        return await self.db.change(statement)


batch = contract(
    "segment_sample.process",
    "分批处理固定输入",
    input=BatchInput,
    output=BatchResult,
    access="segment_sample.write",
    timeout=60,
)


# 游标是本批唯一的起点；每次调用只处理一个固定大小的批次。
@step("取得本批范围", reads=["total", "batch_size"], writes=["start", "end"])
def pick_batch(data: BatchWork, checkpoint: Checkpoint) -> None:
    if data.batch_size <= 0 or data.total < 0:
        raise ValueError("输入规模无效")
    data.start = int(checkpoint.cursor.get("after", 0))
    data.end = min(data.total, data.start + data.batch_size)


# 暂停发生在本批写入之后，SIGKILL 必须撤销本批而保留前面的段。
@step(
    "处理并保存本批",
    reads=["start", "end", "pause_after", "signal_file"],
    writes=["result"],
    saves=True,
)
async def save_batch(data: BatchWork, store: BatchStore) -> None:
    assert await store.save(data.start, data.end) == data.end - data.start
    if data.start == data.pause_after and data.signal_file and not Path(data.signal_file).exists():
        Path(data.signal_file).write_text(str(data.start), encoding="utf-8")
        await asyncio.sleep(3600)
    data.result = BatchResult(processed=data.end)


# 声明提交点；本步骤不直接提交数据库。
@step("声明本批提交点", reads=["start", "end", "total"])
def commit_batch(data: BatchWork, checkpoint: Checkpoint) -> None:
    cursor = {"after": data.end}
    if data.end == data.total:
        checkpoint.finish(rows=data.end - data.start, cursor=cursor)
    else:
        checkpoint.advance(cursor, rows=data.end - data.start)


module = Module(
    "segment_sample",
    "分段验收样例",
    "1",
    provides={
        batch: Flow(
            "逐批处理固定输入",
            work=BatchWork,
            result="result",
            steps=[pick_batch, save_batch, commit_batch],
        )
    },
    store=BatchStore,
    tables=(source, output),
    jobs=(JobPlan(batch, retry=Retry(2, (0,)), repeat_safe=True, segmented=True, lease_seconds=3),),
)
