"""
报价的计算规则：合并明细、计算金额、会员优惠、应付金额、整理返回结果。
全部是纯计算，不读写数据库；规则编号对应 doc/order_quote/rules.md。
"""

from decimal import ROUND_HALF_UP, Decimal

from service.order_quote.data import NothingToQuote, QuoteLine, QuoteLineInput, QuoteView, QuoteWork
from shared.public import Note, condition, step

CENT = Decimal("0.01")
DISCOUNT_RATES = {"none": Decimal("0"), "silver": Decimal("0.05"), "gold": Decimal("0.10")}


# 按 R-01 合并相同商品编码的明细，数量相加，保持首次出现的顺序。
@step("合并明细", reads=["lines"], writes=["merged_lines"], rule="R-01")
def merge_lines(data: QuoteWork) -> None:
    totals: dict[str, int] = {}
    for line in data.lines:
        code = line.code.strip().upper()
        totals[code] = totals.get(code, 0) + line.quantity
    data.merged_lines = [
        QuoteLineInput(code=code, quantity=count) for code, count in totals.items()
    ]


# 按 R-02 计算每行金额和商品合计；不能报价的商品不计入，全部不能报价时报错。
@step(
    "计算金额",
    reads=["merged_lines", "unit_prices", "excluded"],
    writes=["priced_lines", "subtotal"],
    rule="R-02",
)
def count_amounts(data: QuoteWork, note: Note) -> None:
    priced = [
        QuoteLine(
            code=line.code,
            quantity=line.quantity,
            unit_price=data.unit_prices[line.code],
            amount=(data.unit_prices[line.code] * line.quantity).quantize(CENT, ROUND_HALF_UP),
        )
        for line in data.merged_lines
        if line.code in data.unit_prices
    ]
    if not priced:
        raise NothingToQuote()
    if data.excluded:
        note(f"{len(data.excluded)} 个商品没有计入报价：不存在、已停售或尚未定价")
    data.priced_lines = priced
    data.subtotal = sum((line.amount for line in priced), Decimal("0.00"))


# 判断客户是否是会员（银卡或金卡）。
@condition("客户是会员", reads=["member_level"])
def is_member(data: QuoteWork) -> bool:
    return data.member_level != "none"


# 按 R-03 计算会员优惠：银卡 5%，金卡 10%，四舍五入到分。
@step(
    "计算会员优惠",
    reads=["member_level", "subtotal"],
    writes=["discount"],
    rule="R-03",
    when=is_member,
)
def count_discount(data: QuoteWork) -> None:
    rate = DISCOUNT_RATES[data.member_level]
    data.discount = (data.subtotal * rate).quantize(CENT, ROUND_HALF_UP)


# 按 R-04 计算应付金额：商品合计减会员优惠。
@step("计算应付金额", reads=["subtotal", "discount"], writes=["total"], rule="R-04")
def count_total(data: QuoteWork) -> None:
    data.total = data.subtotal - data.discount


# 整理返回给调用方的报价。
@step(
    "整理报价",
    reads=[
        "saved_id",
        "customer",
        "member_level",
        "priced_lines",
        "excluded",
        "subtotal",
        "discount",
        "total",
        "explanation",
        "created_at",
    ],
    writes=["quote"],
)
def build_quote(data: QuoteWork) -> None:
    data.quote = QuoteView(
        id=data.saved_id,
        customer=data.customer,
        member_level=data.member_level,
        lines=data.priced_lines,
        excluded=data.excluded,
        subtotal=data.subtotal,
        discount=data.discount,
        total=data.total,
        explanation=data.explanation,
        status="active",
        created_at=data.created_at,
    )
