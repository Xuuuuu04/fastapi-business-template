"""
订单报价的模块声明：操作与流程的对应、数据访问实现、表、提示词、后台任务和定时计划。
依赖商品目录的 get_prices 操作；这个依赖由步骤的 uses 声明，不需要在这里重复。
"""

from datetime import time

from service.order_quote import flow, public
from service.order_quote.data import ExpireRequest
from service.order_quote.steps.ask_others import explain_quote
from service.order_quote.store.sql import SqlQuoteStore
from service.order_quote.store.tables import quote_lines, quotes
from shared.public import JobPlan, Module, Retry, Schedule

module = Module(
    name="order_quote",
    title="订单报价",
    version="1",
    provides={
        public.create_quote: flow.create_flow,
        public.get_quote: flow.read_flow,
        public.expire_quotes: flow.expire_flow,
    },
    store=SqlQuoteStore,
    tables=(quotes, quote_lines),
    prompts=(explain_quote,),
    jobs=(JobPlan(public.expire_quotes, retry=Retry(times=2), repeat_safe=True, max_queued=10),),
    schedules=(
        Schedule(
            name="expire_quotes_daily",
            title="每天凌晨标记过期报价",
            contract=public.expire_quotes,
            input=ExpireRequest(days=30),
            daily_at=time(2, 0),
        ),
    ),
)
