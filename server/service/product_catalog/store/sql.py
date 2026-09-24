"""
商品目录的数据库实现，SQL 都集中在这里。
不负责提交或回滚，事务由框架按步骤声明安排；唯一约束冲突在保存点内转成业务错误。
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import RowMapping, delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from service.product_catalog.data import CodeUsed, ProductMissing, ProductPage, ProductView
from service.product_catalog.store.tables import products
from shared.public import Db


class SqlProductStore:
    # 使用框架提供的数据库入口。
    def __init__(self, db: Db) -> None:
        self.db = db

    # 按在售状态筛选，返回一页商品和总数。
    async def page(self, offset: int, limit: int, on_sale: bool | None) -> ProductPage:
        query = select(products)
        count = select(func.count()).select_from(products)
        if on_sale is not None:
            query = query.where(products.c.on_sale == on_sale)
            count = count.where(products.c.on_sale == on_sale)
        total = await self.db.scalar(count)
        rows = await self.db.all(query.order_by(products.c.id.desc()).offset(offset).limit(limit))
        return ProductPage(
            items=[view_of(row) for row in rows], total=total, offset=offset, limit=limit
        )

    # 按编号读取商品。
    async def find(self, product_id: int) -> ProductView | None:
        row = await self.db.first(select(products).where(products.c.id == product_id))
        return view_of(row) if row else None

    # 新建商品，编码冲突时转成业务错误。
    async def add(self, code: str, name: str, price: Decimal | None, on_sale: bool) -> ProductView:
        values = {"code": code, "name": name, "price": price, "on_sale": on_sale}
        statement = (
            insert(products).values(**values, updated_at=datetime.now(UTC)).returning(products)
        )
        try:
            async with self.db.savepoint():
                row = await self.db.one(statement)
        except IntegrityError:
            raise CodeUsed(
                f"商品编码 {code} 已被其他商品使用", fields={"code": "编码重复"}
            ) from None
        return view_of(row)

    # 修改商品并记录变更历史，编码冲突或商品不存在时转成业务错误。
    async def change(
        self, product_id: int, code: str, name: str, price: Decimal | None, on_sale: bool
    ) -> ProductView:
        values = {"code": code, "name": name, "price": price, "on_sale": on_sale}
        where = products.c.id == product_id
        quiet = {"updated_at": datetime.now(UTC)}
        try:
            async with self.db.savepoint():
                count = await self.db.update_tracked(products, where, values, quiet=quiet)
        except IntegrityError:
            raise CodeUsed(
                f"商品编码 {code} 已被其他商品使用", fields={"code": "编码重复"}
            ) from None
        if count == 0:
            raise ProductMissing(f"商品 {product_id} 不存在")
        row = await self.db.one(select(products).where(where))
        return view_of(row)

    # 删除商品。
    async def remove(self, product_id: int) -> None:
        if await self.db.change(delete(products).where(products.c.id == product_id)) == 0:
            raise ProductMissing(f"商品 {product_id} 不存在")

    # 查询在售且已定价的商品单价。
    async def prices(self, codes: list[str]) -> dict[str, Decimal]:
        query = select(products.c.code, products.c.price).where(
            products.c.code.in_(codes), products.c.on_sale.is_(True), products.c.price.is_not(None)
        )
        rows = await self.db.all(query)
        return {row["code"]: row["price"] for row in rows}


# 把数据库行转成公开数据。
def view_of(row: RowMapping) -> ProductView:
    return ProductView(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        price=row["price"],
        on_sale=row["on_sale"],
        updated_at=row["updated_at"],
    )
