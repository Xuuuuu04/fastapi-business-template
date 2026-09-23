"""
订单报价的规则测试：每条用例对应 doc/order_quote/rules.md 中确认过的样例。
单独运行步骤，不启动应用；其他模块和大模型都用替身。
"""

from decimal import Decimal

import pytest

from service.order_quote.data import NothingToQuote, QuoteLine, QuoteLineInput, QuoteWork
from service.order_quote.steps.ask_others import read_prices, write_explanation
from service.order_quote.steps.quote_rules import (
    count_amounts,
    count_discount,
    count_total,
    merge_lines,
)
from service.product_catalog import public as catalog
from shared.data.models import Data
from shared.flow.testing import try_step, try_step_async
from shared.model_calls.providers import FakeModel, ModelRequest
from shared.model_calls.service import ModelService


# R-01：编码去空白转大写，相同编码的数量相加，保持首次出现的顺序。
def test_merge_lines() -> None:
    lines = [
        QuoteLineInput(code=" a-1 ", quantity=2),
        QuoteLineInput(code="B-2", quantity=1),
        QuoteLineInput(code="A-1", quantity=1),
    ]
    merged = try_step(merge_lines, QuoteWork, lines=lines).values["merged_lines"]
    assert [(line.code, line.quantity) for line in merged] == [("A-1", 3), ("B-2", 1)]


# R-02：金额 = 单价 × 数量，四舍五入到分；不能报价的商品不计入，并写下数据说明。
def test_count_amounts() -> None:
    merged = [QuoteLineInput(code="A-1", quantity=3), QuoteLineInput(code="C-3", quantity=1)]
    result = try_step(
        count_amounts,
        QuoteWork,
        merged_lines=merged,
        unit_prices={"A-1": Decimal("12.345")},
        excluded=["C-3"],
    )
    assert result.values["subtotal"] == Decimal("37.04")
    assert [line.code for line in result.values["priced_lines"]] == ["A-1"]
    assert result.notes == ["1 个商品没有计入报价：不存在、已停售或尚未定价"]


# R-02：全部商品都不能报价时，报价失败。
def test_nothing_to_quote() -> None:
    with pytest.raises(NothingToQuote):
        try_step(
            count_amounts,
            QuoteWork,
            merged_lines=[QuoteLineInput(code="X", quantity=1)],
            unit_prices={},
            excluded=["X"],
        )


# R-03：银卡 5%、金卡 10%，四舍五入到分。
@pytest.mark.parametrize(
    ("level", "subtotal", "discount"), [("silver", "10.10", "0.51"), ("gold", "37.50", "3.75")]
)
def test_member_discount(level: str, subtotal: str, discount: str) -> None:
    result = try_step(count_discount, QuoteWork, member_level=level, subtotal=Decimal(subtotal))
    assert result.values["discount"] == Decimal(discount)


# R-04：应付金额 = 商品合计 - 会员优惠。
def test_total() -> None:
    result = try_step(count_total, QuoteWork, subtotal=Decimal("37.50"), discount=Decimal("3.75"))
    assert result.values["total"] == Decimal("33.75")


# R-02：向商品目录查询单价，拿不到的编码列入不能报价。
@pytest.mark.anyio
async def test_read_prices_uses_catalog() -> None:
    # 商品目录的替身：只有 A-1 有单价。
    async def fake_prices(query: Data) -> Data:
        assert isinstance(query, catalog.PriceQuery) and query.codes == ["A-1", "Z-9"]
        return catalog.PriceList(prices={"A-1": Decimal("2.00")}, missing=["Z-9"])

    merged = [QuoteLineInput(code="A-1", quantity=1), QuoteLineInput(code="Z-9", quantity=1)]
    result = await try_step_async(
        read_prices, QuoteWork, {"merged_lines": merged}, calls={catalog.get_prices: fake_prices}
    )
    assert result.values == {"unit_prices": {"A-1": Decimal("2.00")}, "excluded": ["Z-9"]}


# R-05：报价说明由大模型生成，提示词中带上客户、明细和金额，结果最长 500 字。
@pytest.mark.anyio
async def test_write_explanation() -> None:
    seen: list[ModelRequest] = []

    # 记下请求，并返回一段超长的说明。
    def answer(request: ModelRequest) -> str:
        seen.append(request)
        return "好" * 800

    service = ModelService(FakeModel({"explain_quote": answer}), concurrency=1, keep_text=False)
    values = {
        "customer": "星河",
        "priced_lines": [
            QuoteLine(code="A-1", quantity=3, unit_price=Decimal("12.50"), amount=Decimal("37.50"))
        ],
        "excluded": [],
        "discount": Decimal("3.75"),
        "total": Decimal("33.75"),
    }
    result = await try_step_async(write_explanation, QuoteWork, values, model=service)
    assert len(result.values["explanation"]) == 500
    assert (
        "星河" in seen[0].user
        and "A-1 × 3" in seen[0].user
        and "33.75" in seen[0].user
        and "无" in seen[0].user
    )
