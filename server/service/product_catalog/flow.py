"""
商品目录的流程：每个公开操作对应一个流程，按顺序列出步骤。
"""

from service.product_catalog.data import (
    CreateWork,
    DeleteWork,
    GetWork,
    ListWork,
    PriceWork,
    UpdateWork,
)
from service.product_catalog.steps.check_product import clean_code
from service.product_catalog.steps.read_products import read_page, read_prices, read_product
from service.product_catalog.steps.save_products import (
    remove_product,
    save_new_product,
    save_product_change,
)
from shared.public import Flow

list_flow = Flow("查询商品", work=ListWork, result="page", steps=[read_page])

get_flow = Flow("读取商品", work=GetWork, result="product", steps=[read_product])

create_flow = Flow(
    "新建商品", work=CreateWork, result="product", steps=[clean_code, save_new_product]
)

update_flow = Flow(
    "修改商品", work=UpdateWork, result="product", steps=[clean_code, save_product_change]
)

delete_flow = Flow("删除商品", work=DeleteWork, result="done", steps=[remove_product])

price_flow = Flow("查询可报价的单价", work=PriceWork, result="prices", steps=[read_prices])
