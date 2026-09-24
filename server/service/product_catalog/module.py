"""
商品目录的模块声明：提供哪些操作、每个操作由哪个流程实现、用哪个数据访问实现、有哪些表。
启用本模块需要在 app/setup/catalog.py 中登记。
"""

from service.product_catalog import flow, public
from service.product_catalog.store.sql import SqlProductStore
from service.product_catalog.store.tables import products
from shared.public import Module

module = Module(
    name="product_catalog",
    title="商品目录",
    version="1",
    provides={
        public.list_products: flow.list_flow,
        public.get_product: flow.get_flow,
        public.create_product: flow.create_flow,
        public.update_product: flow.update_flow,
        public.delete_product: flow.delete_flow,
        public.get_prices: flow.price_flow,
        public.import_products: flow.import_flow,
        public.export_products: flow.export_flow,
    },
    store=SqlProductStore,
    tables=(products,),
)
