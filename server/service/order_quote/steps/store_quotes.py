"""
读写报价的步骤。保存和过期处理声明了 saves=True，在写入事务中执行。
"""

from datetime import UTC, datetime, timedelta

from service.order_quote.data import ExpireResult, ExpireWork, QuoteMissing, QuoteWork, ReadWork
from service.order_quote.store.contract import QuoteStore
from shared.public import step


# 保存报价和明细，得到报价编号和保存时间。
@step(
    "保存报价",
    reads=[
        "customer",
        "member_level",
        "priced_lines",
        "excluded",
        "subtotal",
        "discount",
        "total",
        "explanation",
    ],
    writes=["saved_id", "created_at"],
    saves=True,
)
async def save_quote(data: QuoteWork, store: QuoteStore) -> None:
    amounts = (data.subtotal, data.discount, data.total)
    data.saved_id, data.created_at = await store.add(
        data.customer,
        data.member_level,
        data.priced_lines,
        data.excluded,
        amounts,
        data.explanation,
    )


# 按编号读取报价，不存在时报错。
@step("读取报价", reads=["quote_id"], writes=["quote"])
async def read_quote(data: ReadWork, store: QuoteStore) -> None:
    found = await store.find(data.quote_id)
    if found is None:
        raise QuoteMissing(f"报价 {data.quote_id} 不存在")
    data.quote = found


# 按 R-06 把创建超过指定天数的有效报价标为过期；重复执行结果相同。
@step("标记过期报价", reads=["days"], writes=["result"], rule="R-06", saves=True)
async def expire_old_quotes(data: ExpireWork, store: QuoteStore) -> None:
    before = datetime.now(UTC) - timedelta(days=data.days)
    data.result = ExpireResult(expired=await store.expire(before))
