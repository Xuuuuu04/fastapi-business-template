"""
订单报价的流程。创建报价的步骤顺序：先算、再请大模型写说明、最后保存，
保存（开始写入事务）之后不再调用大模型，避免事务长时间占用数据库连接。
"""

from service.order_quote.data import ExpireWork, QuoteWork, ReadWork
from service.order_quote.steps.ask_others import read_prices, write_explanation
from service.order_quote.steps.quote_rules import (
    build_quote,
    count_amounts,
    count_discount,
    count_total,
    merge_lines,
)
from service.order_quote.steps.store_quotes import expire_old_quotes, read_quote, save_quote
from shared.public import Flow

create_flow = Flow(
    "创建报价",
    work=QuoteWork,
    result="quote",
    steps=[
        merge_lines,
        read_prices,
        count_amounts,
        count_discount,
        count_total,
        write_explanation,
        save_quote,
        build_quote,
    ],
)

read_flow = Flow("读取报价", work=ReadWork, result="quote", steps=[read_quote])

expire_flow = Flow("标记过期报价", work=ExpireWork, result="result", steps=[expire_old_quotes])
