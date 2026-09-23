"""
商品目录的步骤需要的数据访问操作。
步骤只依赖这里的约定；数据库实现见 sql.py。换成其他数据来源时，新写一个实现并在 module.py 中替换。
"""

from decimal import Decimal
from typing import Protocol

from service.product_catalog.data import ProductPage, ProductView


class ProductStore(Protocol):
    # 按在售状态筛选，返回一页商品和总数，最新的在前。
    async def page(self, offset: int, limit: int, on_sale: bool | None) -> ProductPage: ...

    # 按编号读取商品，不存在时返回 None。
    async def find(self, product_id: int) -> ProductView | None: ...

    # 新建商品；编码已被使用时抛出 CodeUsed。
    async def add(
        self, code: str, name: str, price: Decimal | None, on_sale: bool
    ) -> ProductView: ...

    # 修改商品；商品不存在抛出 ProductMissing，编码冲突抛出 CodeUsed。
    async def change(
        self, product_id: int, code: str, name: str, price: Decimal | None, on_sale: bool
    ) -> ProductView: ...

    # 删除商品；不存在时抛出 ProductMissing。
    async def remove(self, product_id: int) -> None: ...

    # 返回在售且已定价的商品单价，按编码对应。
    async def prices(self, codes: list[str]) -> dict[str, Decimal]: ...
