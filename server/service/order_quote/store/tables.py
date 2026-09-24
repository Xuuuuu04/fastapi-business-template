"""
订单报价的数据库表：报价主表和明细表。表名以模块名开头，只有本模块的 store 可以读写。
报价按负责人隔离（R-07）：没有 order_quote.manage 权限的调用者只能读写自己创建的报价。
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Table, Text

from shared.public import ExactNumber, UtcTime, metadata, owner_column

quotes = Table(
    "order_quote_quotes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("customer", String(80), nullable=False),
    Column("member_level", String(10), nullable=False),
    Column("subtotal", ExactNumber(14, 2), nullable=False),
    Column("discount", ExactNumber(14, 2), nullable=False),
    Column("total", ExactNumber(14, 2), nullable=False),
    Column("excluded", Text, nullable=False),
    Column("explanation", Text, nullable=False),
    Column("status", String(10), nullable=False),
    Column("created_at", UtcTime(), nullable=False),
    owner_column(see_all="order_quote.manage"),
    Index("ix_order_quote_quotes_status_created", "status", "created_at"),
)

quote_lines = Table(
    "order_quote_lines",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "quote_id", Integer, ForeignKey("order_quote_quotes.id", ondelete="CASCADE"), nullable=False
    ),
    Column("code", String(40), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price", ExactNumber(14, 2), nullable=False),
    Column("amount", ExactNumber(14, 2), nullable=False),
    Index("ix_order_quote_lines_quote", "quote_id"),
)
