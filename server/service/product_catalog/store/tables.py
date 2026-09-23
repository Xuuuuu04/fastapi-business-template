"""
商品目录的数据库表。表名以模块名开头，只有本模块的 store 可以读写。
"""

from sqlalchemy import Boolean, Column, Integer, String, Table

from shared.public import ExactNumber, UtcTime, metadata

products = Table(
    "product_catalog_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(40), nullable=False, unique=True),
    Column("name", String(80), nullable=False),
    Column("price", ExactNumber(14, 2), nullable=True),
    Column("on_sale", Boolean, nullable=False, default=True),
    Column("updated_at", UtcTime(), nullable=False),
)
