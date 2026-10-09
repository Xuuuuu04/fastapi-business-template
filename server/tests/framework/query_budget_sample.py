"""
独立查询额度样例：逐行读取与批量读取共用数据，不登记到产品目录。
"""

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


# 要读取的编号和读取方式。
class Input(Data):
    size: int = meaning("读取数量", default=25)
    batch: bool = meaning("是否批量读取", default=False)


# 实际读取条数。
class Output(Data):
    rows: int = meaning("读到的行数")


# 查询步骤共享的字段。
class Work(WorkData):
    size: int = meaning("读取数量")
    batch: bool = meaning("是否批量读取")
    result: Output = meaning("查询结果")


# SQL只放在存储函数里，框架可定位到同一函数的重复执行。
class Store:
    # 注入Db。
    def __init__(self, db: Db) -> None:
        self.db = db

    # 坏样例每次只读一条。
    async def find_one(self, identity: int) -> bool:
        return await self.db.first(select(items).where(items.c.id == identity)) is not None

    # 好样例一次批量读取。
    async def find_many(self, size: int) -> int:
        return len(await self.db.all(select(items).where(items.c.id < size)))


# 同样输入分别走循环或批量读取。
@step("读取商品", reads=["size", "batch"], writes=["result"])
async def load_items(data: Work, store: Store) -> None:
    if data.batch:
        count = await store.find_many(data.size)
    else:
        count = 0
        for identity in range(data.size):
            count += await store.find_one(identity)
    data.result = Output(rows=count)


# 每次独立声明便于测试额度、旧操作、启动错误。
SAMPLE_BUDGET = QueryBudget(queries=20, rows=5000, bytes=64000, repeated=20)


# 在测试内建立独立模块。
def module_for(budget: QueryBudget | None = SAMPLE_BUDGET) -> Module:
    item = contract(
        "query_sample.read",
        "查询样例",
        input=Input,
        output=Output,
        access="public",
        query_budget=budget,
    )
    flow = Flow("读取", work=Work, result="result", steps=[load_items])
    return Module(
        "query_sample", "查询样例", "1.0.0", provides={item: flow}, store=Store, tables=(items,)
    )


# 检查超额失败发生在事务提交前。
class SavingStore(Store):
    # 固定插入一行便于核对回滚。
    async def add(self) -> None:
        from sqlalchemy import insert

        await self.db.change(insert(items).values(id=999, name="待回滚"))


# 写入步骤与后续读取共用事务。
@step("保存样例", saves=True)
async def save_item(data: Work, store: SavingStore) -> None:
    await store.add()
