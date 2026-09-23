"""
保存商品的步骤。声明了 saves=True，在写入事务中执行，操作结束时由框架提交。
"""

from service.product_catalog.data import CreateWork, DeleteWork, UpdateWork
from service.product_catalog.store.contract import ProductStore
from shared.public import Nothing, step


# 保存新商品。
@step(
    "保存新商品", reads=["clean_code", "name", "price", "on_sale"], writes=["product"], saves=True
)
async def save_new_product(data: CreateWork, store: ProductStore) -> None:
    data.product = await store.add(data.clean_code, data.name, data.price, data.on_sale)


# 保存商品修改。
@step(
    "保存商品修改",
    reads=["product_id", "clean_code", "name", "price", "on_sale"],
    writes=["product"],
    saves=True,
)
async def save_product_change(data: UpdateWork, store: ProductStore) -> None:
    data.product = await store.change(
        data.product_id, data.clean_code, data.name, data.price, data.on_sale
    )


# 删除商品。
@step("删除商品", reads=["product_id"], writes=["done"], saves=True)
async def remove_product(data: DeleteWork, store: ProductStore) -> None:
    await store.remove(data.product_id)
    data.done = Nothing()
