"""
导入导出用的表格文件读写：CSV（UTF-8，可带 BOM，Excel 另存的 CSV 也能读）和 Excel（.xlsx）。
读取时按表头对应字段，每行带上在文件中的行号，便于逐行报告错误；只做格式转换，不做业务检查。
文件太大、没有表头、缺少必需的列时报 invalid_input，不静默跳过。
"""

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from openpyxl import Workbook, load_workbook

from shared.errors.framework import InvalidInput

MAX_ROWS = 5000
Kind = Literal["csv", "xlsx"]
MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# 读取表格文件，返回 (行号, {字段: 文字}) 列表。columns 把表头（中文或字段名）对应到字段名，
# required 是必需的字段及其表头名称，缺少时按表头名称报错。
def read_sheet(
    content: bytes, filename: str, columns: Mapping[str, str], required: Mapping[str, str]
) -> list[tuple[int, dict[str, str]]]:
    raw = read_xlsx(content) if filename.lower().endswith(".xlsx") else read_csv(content)
    if not raw:
        raise InvalidInput("文件是空的，第一行应是表头")
    header = [columns.get(str(cell).strip(), "") for cell in raw[0]]
    missing = [title for name, title in required.items() if name not in header]
    if missing:
        raise InvalidInput(f"表头缺少必需的列：{'、'.join(missing)}")
    body = raw[1:]
    if len(body) > MAX_ROWS:
        raise InvalidInput(f"一次最多导入 {MAX_ROWS} 行，文件有 {len(body)} 行")
    rows = []
    for number, cells in enumerate(body, start=2):
        values = {field: text_of(cell) for field, cell in zip(header, cells, strict=False) if field}
        if any(values.values()):
            rows.append((number, values))
    return rows


# 读取 CSV；不是 UTF-8 编码时报错，提示另存为 UTF-8。
def read_csv(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidInput("CSV 文件不是 UTF-8 编码，请在 Excel 中另存为“CSV UTF-8”") from None
    return [row for row in csv.reader(io.StringIO(text))]


# 读取 Excel 的第一个工作表。
def read_xlsx(content: bytes) -> list[list[Any]]:
    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as error:
        raise InvalidInput(f"无法读取 Excel 文件（{type(error).__name__}）") from None
    sheet = book.worksheets[0]
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    book.close()
    return rows


# 单元格转成去掉首尾空白的文字；空单元格是空文字。
def text_of(cell: Any) -> str:
    return "" if cell is None else str(cell).strip()


# 生成表格文件：columns 把字段名对应到表头文字，按顺序输出。
def write_sheet(rows: Sequence[Mapping[str, Any]], columns: Mapping[str, str], kind: Kind) -> bytes:
    header = list(columns.values())
    body = [[plain(row.get(field)) for field in columns] for row in rows]
    if kind == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerows([header, *body])
        return buffer.getvalue().encode("utf-8-sig")
    book = Workbook(write_only=True)
    sheet = book.create_sheet()
    for line in [header, *body]:
        sheet.append(line)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


# 导出时的单元格值：空值写成空文字，布尔值写成“是”“否”，其余转成文字。
def plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)
