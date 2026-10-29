import pytest

from shared.errors.framework import InvalidInput
from shared.exchange import sheets
from shared.exchange.sheets import read_sheet, write_sheet

COLUMNS = {"编码": "code", "名称": "name"}
REQUIRED = {"code": "编码"}


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_round_trip(kind: sheets.Kind) -> None:
    rows = [{"code": "A", "name": "甲"}, {"code": "", "name": ""}, {"code": "B", "name": "乙"}]
    content = write_sheet(rows, {"code": "编码", "name": "名称"}, kind)
    found = read_sheet(content, f"f.{kind}", COLUMNS, REQUIRED)
    assert found == [(2, {"code": "A", "name": "甲"}), (4, {"code": "B", "name": "乙"})]


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
