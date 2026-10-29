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


class BatchInput(Data):
    total: int = meaning("固定输入总行数", default=100000)
    batch_size: int = meaning("每批处理行数", default=5000)
    pause_after: int = meaning("在此前已提交行数后暂停，负数表示不暂停", default=-1)
    signal_file: str = meaning("强杀验收的暂停信号文件", default="")


class BatchResult(Data):
    processed: int = meaning("累计处理行数")


class BatchWork(BatchInput, WorkData):
    start: int = meaning("上一个已提交的位置", default=0)
    end: int = meaning("本批结束位置", default=0)
    result: BatchResult = meaning("本批处理结果")


class BatchStore:
    def __init__(self, db: Db) -> None:
        self.db = db

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


@step("取得本批范围", reads=["total", "batch_size"], writes=["start", "end"])
def pick_batch(data: BatchWork, checkpoint: Checkpoint) -> None:
    if data.batch_size <= 0 or data.total < 0:
        raise ValueError("输入规模无效")
    data.start = int(checkpoint.cursor.get("after", 0))
    data.end = min(data.total, data.start + data.batch_size)


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
