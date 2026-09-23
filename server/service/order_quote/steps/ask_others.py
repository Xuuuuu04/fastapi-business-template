"""
需要调用其他模块或大模型的步骤：向商品目录查询单价、请大模型写报价说明。
提示词在本文件声明，并在 module.py 中登记。
"""

from pathlib import Path

from service.order_quote.data import QuoteWork
from service.product_catalog import public as catalog
from shared.public import Call, Model, prompt, step

explain_quote = prompt(
    "explain_quote",
    "报价说明",
    file=Path(__file__).parents[1] / "prompts" / "explain_quote.md",
    version="1",
    max_tokens=300,
)

MAX_EXPLANATION = 500


# 按 R-02 向商品目录查询单价，拿不到单价的编码记为不能报价。
@step(
    "查询商品单价",
    reads=["merged_lines"],
    writes=["unit_prices", "excluded"],
    uses=[catalog.get_prices],
    rule="R-02",
)
async def read_prices(data: QuoteWork, call: Call) -> None:
    codes = [line.code for line in data.merged_lines]
    found = await call(catalog.get_prices, catalog.PriceQuery(codes=codes))
    data.unit_prices = found.prices
    data.excluded = found.missing


# 按 R-05 请大模型写一到两句给客户看的报价说明，最长 500 字。
@step(
    "生成报价说明",
    reads=["customer", "priced_lines", "excluded", "discount", "total"],
    writes=["explanation"],
    prompts=[explain_quote],
    rule="R-05",
)
async def write_explanation(data: QuoteWork, model: Model) -> None:
    items = "；".join(f"{line.code} × {line.quantity}" for line in data.priced_lines)
    text = await model.ask(
        explain_quote,
        customer=data.customer,
        items=items,
        discount=data.discount,
        total=data.total,
        excluded="、".join(data.excluded) or "无",
    )
    data.explanation = text.strip()[:MAX_EXPLANATION]
