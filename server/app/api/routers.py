"""
全部路由的清单。新增模块的接口文件后在这里登记；tools.new_module 会自动加入。
"""

from fastapi import APIRouter

from app.api.system import health, jobs, runs, structure
from app.api.v1 import order_quote, product_catalog

ROUTERS: list[APIRouter] = [
    health.router,
    structure.router,
    runs.router,
    jobs.router,
    product_catalog.router,
    order_quote.router,
]
