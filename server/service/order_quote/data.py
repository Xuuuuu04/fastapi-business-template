"""
订单报价的公开数据、流程数据和业务错误。字段含义和计算规则见 doc/order_quote/rules.md。
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from shared.public import BusinessError, Data, Kind, WorkData, meaning

MemberLevel = Literal["none", "silver", "gold"]
QuoteStatus = Literal["active", "expired"]


class QuoteLineInput(Data):
    code: str = meaning("商品编码", example="A-100", min_length=1, max_length=40)
    quantity: int = meaning("数量", example=2, ge=1, le=10000)


class QuoteRequest(Data):
    customer: str = meaning("客户名称", example="星河贸易", min_length=1, max_length=80)
    member_level: MemberLevel = meaning(
        "会员等级：none 非会员，silver 银卡，gold 金卡", rule="R-03"
    )
    lines: list[QuoteLineInput] = meaning("报价明细", min_length=1, max_length=100)


class QuoteLine(Data):
    code: str = meaning("商品编码")
    quantity: int = meaning("数量；同一编码的多行已合并", rule="R-01")
    unit_price: Decimal = meaning("单价", unit="元", rule="R-02")
    amount: Decimal = meaning("金额 = 单价 × 数量", unit="元", rule="R-02")


class QuoteView(Data):
    id: int = meaning("报价编号")
    customer: str = meaning("客户名称")
    member_level: MemberLevel = meaning("会员等级", rule="R-03")
    lines: list[QuoteLine] = meaning("计入报价的明细", rule="R-02")
    excluded: list[str] = meaning("没有计入报价的商品编码：不存在、停售或未定价", rule="R-02")
    subtotal: Decimal = meaning("商品合计", unit="元", rule="R-02")
    discount: Decimal = meaning("会员优惠", unit="元", rule="R-03")
    total: Decimal = meaning("应付金额", unit="元", rule="R-04")
    explanation: str = meaning("给客户看的报价说明，由大模型生成", rule="R-05")
    status: QuoteStatus = meaning("报价状态：active 有效，expired 已过期", rule="R-06")
    created_at: datetime = meaning("创建时间（UTC）")


class QuoteId(Data):
    quote_id: int = meaning("报价编号", gt=0)


class ExpireRequest(Data):
    days: int = meaning("创建超过多少天的有效报价标为过期", rule="R-06", default=30, ge=1, le=3650)


class ExpireResult(Data):
    expired: int = meaning("本次标为过期的报价数量")


class QuoteMissing(BusinessError):
    code = "quote_missing"
    kind = Kind.NOT_FOUND
    message = "报价不存在"


class NothingToQuote(BusinessError):
    code = "nothing_to_quote"
    kind = Kind.INVALID
    message = "所有商品都不能报价：不存在、已停售或尚未定价"


class QuoteWork(WorkData):
    customer: str = meaning("客户名称")
    member_level: MemberLevel = meaning("会员等级", rule="R-03")
    lines: list[QuoteLineInput] = meaning("调用方提交的明细")
    merged_lines: list[QuoteLineInput] = meaning("合并相同编码后的明细", rule="R-01")
    unit_prices: dict[str, Decimal] = meaning("可报价商品的单价", unit="元", rule="R-02")
    excluded: list[str] = meaning("不能报价的商品编码", rule="R-02")
    priced_lines: list[QuoteLine] = meaning("计入报价的明细", rule="R-02")
    subtotal: Decimal = meaning("商品合计", unit="元", rule="R-02", log_value=True)
    discount: Decimal = meaning(
        "会员优惠", unit="元", rule="R-03", log_value=True, default=Decimal("0.00")
    )
    total: Decimal = meaning("应付金额", unit="元", rule="R-04", log_value=True)
    explanation: str = meaning("报价说明", rule="R-05")
    saved_id: int = meaning("保存后的报价编号", log_value=True)
    created_at: datetime = meaning("保存时间（UTC）")
    quote: QuoteView = meaning("返回给调用方的报价")


class ReadWork(WorkData):
    quote_id: int = meaning("报价编号")
    quote: QuoteView = meaning("读取到的报价")


class ExpireWork(WorkData):
    days: int = meaning("过期天数", rule="R-06")
    result: ExpireResult = meaning("处理结果")
