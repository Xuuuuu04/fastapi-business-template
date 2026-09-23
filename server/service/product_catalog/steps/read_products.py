"""
读取商品的步骤。只读，不能写入数据库。
"""

from service.product_catalog.data import GetWork, ListWork, PriceList, PriceWork, ProductMissing
from service.product_catalog.store.contract import ProductStore
from shared.public import step


# 按筛选条件读取一页商品。
@step("读取商品列表", reads=["offset", "limit", "on_sale"], writes=["page"])
async def read_page(data: ListWork, store: ProductStore) -> None:
    data.page = await store.page(data.offset, data.limit, data.on_sale)


# 按编号读取一个商品，不存在时报错。
@step("读取商品", reads=["product_id"], writes=["product"])
async def read_product(data: GetWork, store: ProductStore) -> None:
    found = await store.find(data.product_id)
    if found is None:
        raise ProductMissing(f"商品 {data.product_id} 不存在")
    data.product = found


# 按 R-02 读取可以报价的单价：在售且已定价；其余编码列入 missing。
@step("读取可报价单价", reads=["codes"], writes=["prices"], rule="R-02")
async def read_prices(data: PriceWork, store: ProductStore) -> None:
    wanted = sorted(set(data.codes))
    found = await store.prices(wanted)
    data.prices = PriceList(prices=found, missing=[code for code in wanted if code not in found])
