"""
表格文件读写：CSV 与 Excel 往返一致，行号对应文件中的行，空行跳过；
空文件、缺少必需的列、不是 UTF-8 的 CSV、超过行数上限、损坏的 Excel 都报 invalid_input。
"""

import pytest

from shared.errors.framework import InvalidInput
from shared.exchange import sheets
from shared.exchange.sheets import read_sheet, write_sheet

COLUMNS = {"编码": "code", "名称": "name"}
REQUIRED = {"code": "编码"}


# 写出再读回，内容一致；行号从 2 开始，空行跳过但行号照算。
@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_round_trip(kind: sheets.Kind) -> None:
    rows = [{"code": "A", "name": "甲"}, {"code": "", "name": ""}, {"code": "B", "name": "乙"}]
    content = write_sheet(rows, {"code": "编码", "name": "名称"}, kind)
    found = read_sheet(content, f"f.{kind}", COLUMNS, REQUIRED)
    assert found == [(2, {"code": "A", "name": "甲"}), (4, {"code": "B", "name": "乙"})]


# 格式问题直接报错，不静默跳过。
def test_bad_files(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        (b"", "f.csv", "文件是空的"),
        ("名称\n甲\n".encode(), "f.csv", "表头缺少必需的列：编码"),
        ("编码\n甲\n".encode("gbk"), "f.csv", "不是 UTF-8"),
        (b"not excel", "f.xlsx", "无法读取 Excel"),
    ]
    for content, name, text in cases:
        with pytest.raises(InvalidInput) as caught:
            read_sheet(content, name, COLUMNS, REQUIRED)
        assert text in caught.value.detail
    monkeypatch.setattr(sheets, "MAX_ROWS", 2)
    with pytest.raises(InvalidInput):
        read_sheet("编码\nA\nB\nC\n".encode(), "f.csv", COLUMNS, REQUIRED)
