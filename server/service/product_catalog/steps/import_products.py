"""
批量导入与导出的步骤（R-03、R-04）：逐行检查、保存检查通过的行、整理结果，读取要导出的商品。
逐行检查是纯计算，保存在写入事务中进行。
"""

from decimal import Decimal, InvalidOperation

from service.product_catalog.data import (
    ExportWork,
    ImportLine,
    ImportResult,
    ImportWork,
    ProductInput,
    RowProblem,
)
from service.product_catalog.store.contract import ProductStore
from shared.public import Note, step

YES = {"", "是", "true", "1", "在售"}
NO = {"否", "false", "0", "停售"}
CENT = Decimal("0.01")


# 按 R-03 逐行检查：编码整理与重复、名称、单价、在售；有问题的行列入 problems，不导入。
@step("逐行检查", reads=["lines"], writes=["valid", "problems"], rule="R-03")
def check_rows(data: ImportWork, note: Note) -> None:
    seen: set[str] = set()
    valid, problems = [], []
    for line in data.lines:
        found = line_problem(line, seen)
        if found:
            problems.append(RowProblem(row=line.row, message=found))
            continue
        seen.add(line.code.strip().upper())
        valid.append(to_input(line))
    if problems:
        note(f"{len(problems)} 行没有导入，原因见结果")
    data.valid, data.problems = valid, problems


# 返回一行的问题说明；没有问题时返回空文字。
def line_problem(line: ImportLine, seen: set[str]) -> str:
    code, name = line.code.strip().upper(), line.name.strip()
    if not code or len(code) > 40:
        return "编码不能为空，最长 40 字"
    if code in seen:
        return "文件中编码重复"
    if not name or len(name) > 80:
        return "名称不能为空，最长 80 字"
    if line.price.strip() and price_of(line.price) is None:
        return "单价必须是不小于 0、最多两位小数的数字"
    if line.on_sale.strip().lower() not in YES | NO:
        return "在售只能写“是”或“否”"
    return ""


# 单价原文转成金额；格式不对、为负数或超过两位小数时返回 None。
def price_of(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value != value.quantize(CENT):
        return None
    return value.quantize(CENT)


# 检查通过的一行转成商品输入。
def to_input(line: ImportLine) -> ProductInput:
    price = price_of(line.price) if line.price.strip() else None
    return ProductInput(
        code=line.code.strip().upper(),
        name=line.name.strip(),
        price=price,
        on_sale=line.on_sale.strip().lower() not in NO,
    )


# 按 R-03 保存：编码已存在就修改（记入变更历史），否则新建。
@step("保存导入的商品", reads=["valid"], writes=["created", "updated"], rule="R-03", saves=True)
async def save_rows(data: ImportWork, store: ProductStore) -> None:
    data.created, data.updated = await store.upsert(data.valid)


# 整理导入结果。
@step("整理导入结果", reads=["created", "updated", "problems"], writes=["result"], rule="R-03")
def build_import_result(data: ImportWork) -> None:
    data.result = ImportResult(created=data.created, updated=data.updated, problems=data.problems)


# 按 R-04 读取要导出的商品。
@step("读取导出的商品", reads=["on_sale"], writes=["result"], rule="R-04")
async def read_export(data: ExportWork, store: ProductStore) -> None:
    data.result = await store.export(data.on_sale)
