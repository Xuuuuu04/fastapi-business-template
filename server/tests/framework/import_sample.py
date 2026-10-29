from decimal import Decimal

from sqlalchemy import Column, Integer, MetaData, String, Table, insert

from shared.public import (
    Checkpoint,
    Data,
    Db,
    ExactNumber,
    Flow,
    ImportPlan,
    ImportReference,
    JobPlan,
    Module,
    Reconcile,
    WorkData,
    contract,
    meaning,
    step,
)

sample_metadata = MetaData()
parents = Table("import_sample_parents", sample_metadata, Column("id", Integer, primary_key=True))
rows = Table(
    "import_sample_rows",
    sample_metadata,
    Column("id", Integer, primary_key=True),
    Column("amount", ExactNumber(18, 2)),
    Column("quality", String),
    Column("parent_id", Integer),
)


class Input(Data):
    omit: bool = meaning("故意漏掉最后一行", default=False)
    bad_quality: bool = meaning("故意缺质量字段", default=False)
    bad_reference: bool = meaning("故意缺引用", default=False)


class Result(Data):
    code: int = meaning("模拟导入工具返回码", default=0)


class Work(WorkData, Input):
    result: Result = meaning("导入工具返回")


class Store:
    def __init__(self, db: Db):
        self.db = db

    async def save(self, number: int, omit: bool, bad_quality: bool, bad_reference: bool) -> None:
        if number == 0:
            await self.db.change(insert(parents).values(id=1))
        if not (number == 1 and omit):
            await self.db.change(
                insert(rows).values(
                    id=number + 1,
                    amount=Decimal("0.10") * (number + 1),
                    quality=None if bad_quality else "source",
                    parent_id=2 if bad_reference else 1,
                )
            )


operation = contract(
    "import_sample.load",
    "导入固定来源",
    input=Input,
    output=Result,
    access="public",
    effect="command",
)


@step("保存一批", reads=["omit", "bad_quality", "bad_reference"], writes=["result"], saves=True)
async def save(data: Work, store: Store, checkpoint: Checkpoint) -> None:
    number = int(checkpoint.cursor.get("after", 0))
    await store.save(number, data.omit, data.bad_quality, data.bad_reference)
    if number == 1:
        checkpoint.finish(rows=0 if data.omit else 1, cursor={"after": 2})
    else:
        checkpoint.advance({"after": 1}, rows=1)
    data.result = Result()


plan = ImportPlan(
    "source-commit-42",
    "fixed-two-rows",
    reconcile=Reconcile(
        rows,
        rows=2,
        sums={"amount": Decimal("0.30")},
        non_null={"quality": 1},
        references=(ImportReference("parent_id", parents.c.id),),
    ),
)
module = Module(
    "import_sample",
    "导入对账样例",
    "1",
    provides={
        operation: Flow("分批导入", work=Work, result="result", steps=[save]),
    },
    store=Store,
    tables=(parents, rows),
    jobs=(JobPlan(operation, segmented=True, repeat_safe=True, import_plan=plan),),
    kind="capability",
)
