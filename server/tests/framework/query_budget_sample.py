from sqlalchemy import Column, Integer, MetaData, String, Table, select

from shared.public import (
    Data,
    Db,
    Flow,
    Module,
    QueryBudget,
    WorkData,
    contract,
    meaning,
    step,
)

sample_metadata = MetaData()
items = Table(
    "query_sample_items",
    sample_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
)


class Input(Data):
    size: int = meaning("读取数量", default=25)
    batch: bool = meaning("是否批量读取", default=False)


class Output(Data):
    rows: int = meaning("读到的行数")


class Work(WorkData):
    size: int = meaning("读取数量")
    batch: bool = meaning("是否批量读取")
    result: Output = meaning("查询结果")


class Store:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def find_one(self, identity: int) -> bool:
        return await self.db.first(select(items).where(items.c.id == identity)) is not None

    async def find_many(self, size: int) -> int:
        return len(await self.db.all(select(items).where(items.c.id < size)))


@step("读取商品", reads=["size", "batch"], writes=["result"])
async def load_items(data: Work, store: Store) -> None:
    if data.batch:
        count = await store.find_many(data.size)
    else:
        count = 0
        for identity in range(data.size):
            count += await store.find_one(identity)
    data.result = Output(rows=count)


SAMPLE_BUDGET = QueryBudget(queries=20, rows=5000, bytes=64000, repeated=20)


def module_for(budget: QueryBudget | None = SAMPLE_BUDGET) -> Module:
    item = contract(
        "query_sample.read",
        "查询样例",
        input=Input,
        output=Output,
        access="public",
        query_budget=budget,
        effect="command",
    )
    flow = Flow("读取", work=Work, result="result", steps=[load_items])
    return Module(
        "query_sample",
        "查询样例",
        "1.0.0",
        provides={item: flow},
        store=Store,
        tables=(items,),
        kind="capability",
    )


class SavingStore(Store):
    async def add(self) -> None:
        from sqlalchemy import insert

        await self.db.change(insert(items).values(id=999, name="待回滚"))


@step("保存样例", saves=True)
async def save_item(data: Work, store: SavingStore) -> None:
    await store.add()
