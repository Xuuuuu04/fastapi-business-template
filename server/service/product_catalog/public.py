"""
商品目录对外提供的操作约定和公开数据。
其他模块和接口层只能导入本文件；实现写在 flow.py 和 steps/ 中，由 module.py 对应起来。
"""

from service.product_catalog.data import (
    CodeUsed,
    ExportQuery,
    ImportLine,
    ImportRequest,
    ImportResult,
    PriceList,
    PriceQuery,
    ProductChange,
    ProductId,
    ProductInput,
    ProductList,
    ProductMissing,
    ProductPage,
    ProductQuery,
    ProductView,
    RowProblem,
)
from shared.public import Nothing, contract

list_products = contract(
    "product_catalog.list_products",
    "查询商品",
    input=ProductQuery,
    output=ProductPage,
    access="product_catalog.read",
)

get_product = contract(
    "product_catalog.get_product",
    "读取商品",
    input=ProductId,
    output=ProductView,
    access="product_catalog.read",
    errors=(ProductMissing,),
)

create_product = contract(
    "product_catalog.create_product",
    "新建商品",
    input=ProductInput,
    output=ProductView,
    access="product_catalog.write",
    errors=(CodeUsed,),
)

update_product = contract(
    "product_catalog.update_product",
    "修改商品",
    input=ProductChange,
    output=ProductView,
    access="product_catalog.write",
    errors=(ProductMissing, CodeUsed),
)

delete_product = contract(
    "product_catalog.delete_product",
    "删除商品",
    input=ProductId,
    output=Nothing,
    access="product_catalog.write",
    errors=(ProductMissing,),
)

import_products = contract(
    "product_catalog.import_products",
    "批量导入商品",
    input=ImportRequest,
    output=ImportResult,
    access="product_catalog.write",
    audit=True,
)
export_products = contract(
    "product_catalog.export_products",
    "导出商品",
    input=ExportQuery,
    output=ProductList,
    access="product_catalog.read",
)
get_prices = contract(
    "product_catalog.get_prices",
    "查询可报价的单价",
    input=PriceQuery,
    output=PriceList,
    access="product_catalog.read",
    entry=False,
)

__all__ = [
    "CodeUsed",
    "ExportQuery",
    "ImportLine",
    "ImportRequest",
    "ImportResult",
    "PriceList",
    "PriceQuery",
    "ProductChange",
    "ProductId",
    "ProductInput",
    "ProductList",
    "ProductMissing",
    "ProductPage",
    "ProductQuery",
    "ProductView",
    "RowProblem",
    "create_product",
    "delete_product",
    "export_products",
    "get_prices",
    "get_product",
    "import_products",
    "list_products",
    "update_product",
]
