"""
订单报价对外提供的操作约定和公开数据。其他模块和接口层只能导入本文件。
"""

from service.order_quote.data import (
    ExpireRequest,
    ExpireResult,
    NothingToQuote,
    QuoteId,
    QuoteLine,
    QuoteLineInput,
    QuoteMissing,
    QuoteRequest,
    QuoteView,
)
from shared.public import contract

create_quote = contract(
    "order_quote.create_quote",
    "创建报价",
    input=QuoteRequest,
    output=QuoteView,
    access="order_quote.write",
    errors=(NothingToQuote,),
    timeout=90,
)

get_quote = contract(
    "order_quote.get_quote",
    "读取报价",
    input=QuoteId,
    output=QuoteView,
    access="order_quote.read",
    errors=(QuoteMissing,),
)

expire_quotes = contract(
    "order_quote.expire_quotes",
    "标记过期报价",
    input=ExpireRequest,
    output=ExpireResult,
    access="order_quote.manage",
    timeout=120,
)

__all__ = [
    "ExpireRequest",
    "ExpireResult",
    "NothingToQuote",
    "QuoteId",
    "QuoteLine",
    "QuoteLineInput",
    "QuoteMissing",
    "QuoteRequest",
    "QuoteView",
    "create_quote",
    "expire_quotes",
    "get_quote",
]
