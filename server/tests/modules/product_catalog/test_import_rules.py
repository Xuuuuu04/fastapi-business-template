"""
商品批量导入的规则测试（R-03）：预期值来自 doc/product_catalog/rules.md 中 R-03 的样例表。
"""

from decimal import Decimal

from service.product_catalog.data import ImportLine, ImportWork
from service.product_catalog.steps.import_products import check_rows
from shared.flow.testing import try_step


# R-03：编码整理与文件内重复、名称必填、单价格式；有问题的行不导入，列出行号和原因。
def test_check_rows_follows_samples() -> None:
    lines = [
        ImportLine(row=2, code=" a-1 ", name="甲", price="12.50", on_sale="是"),
        ImportLine(row=3, code="A-1", name="乙", on_sale="否"),
        ImportLine(row=4, code="B-2", price="3.00"),
        ImportLine(row=5, code="C-3", name="丙", price="-1"),
    ]
    result = try_step(check_rows, ImportWork, lines=lines)
    [only] = result.values["valid"]
    assert (only.code, only.name, only.price, only.on_sale) == ("A-1", "甲", Decimal("12.50"), True)
    problems = [(item.row, item.message) for item in result.values["problems"]]
    assert problems == [
        (3, "文件中编码重复"),
        (4, "名称不能为空，最长 80 字"),
        (5, "单价必须是不小于 0、最多两位小数的数字"),
    ]
    assert result.notes == ["3 行没有导入，原因见结果"]


# R-03：单价为空表示尚未定价，在售为空表示在售，“否”表示停售；超过两位小数和“也许”都报错。
def test_empty_price_and_sale_flags() -> None:
    lines = [
        ImportLine(row=2, code="D-4", name="丁"),
        ImportLine(row=3, code="E-5", name="戊", on_sale="否"),
        ImportLine(row=4, code="F-6", name="己", price="1.005"),
        ImportLine(row=5, code="G-7", name="庚", on_sale="也许"),
    ]
    result = try_step(check_rows, ImportWork, lines=lines)
    assert [(item.price, item.on_sale) for item in result.values["valid"]] == [
        (None, True),
        (None, False),
    ]
    assert [item.row for item in result.values["problems"]] == [4, 5]
