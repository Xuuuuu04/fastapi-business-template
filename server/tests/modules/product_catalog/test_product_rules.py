"""
商品目录的规则测试：每条用例对应 doc/product_catalog/rules.md 中确认过的样例。
"""

from decimal import Decimal

import pytest

from service.product_catalog.data import CreateWork, PriceWork
from service.product_catalog.steps.check_product import clean_code
from service.product_catalog.steps.read_products import read_prices
from shared.flow.testing import try_step, try_step_async


# R-01：商品编码去掉首尾空白并转成大写。
def test_clean_code() -> None:
    assert try_step(clean_code, CreateWork, code="  a-100 ").values["clean_code"] == "A-100"


class PriceOnlyStore:
    # 只实现查询单价的替身：数据库中只有 A-1 在售且已定价。
    async def prices(self, codes: list[str]) -> dict[str, Decimal]:
        return {code: Decimal("9.90") for code in codes if code == "A-1"}


# R-02：只返回在售且已定价的单价，其余编码去重排序后列入 missing。
@pytest.mark.anyio
async def test_read_prices() -> None:
    result = await try_step_async(
        read_prices, PriceWork, {"codes": ["B-2", "A-1", "B-2"]}, store=PriceOnlyStore()
    )
    prices = result.values["prices"]
    assert prices.prices == {"A-1": Decimal("9.90")} and prices.missing == ["B-2"]
