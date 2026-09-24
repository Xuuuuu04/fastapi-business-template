"""
商品导入导出的接口测试（R-03、R-04）：上传 CSV 和 Excel，逐行报告问题；导出的文件可以直接再导入。
"""

import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.testing_app import KEY, READER

CSV = "编码,名称,单价,在售\n a-1 ,甲,12.50,是\nA-1,乙,,否\nB-2,,3.00,\nC-3,丙,-1,\n"


# R-03：CSV 导入按样例新建一行、报告三行问题；再次导入同一编码时改为修改并记入变更历史。
def test_import_csv(client: TestClient) -> None:
    upload = {"upload": ("商品.csv", CSV.encode("utf-8-sig"), "text/csv")}
    reply = client.post("/api/v1/products/import", files=upload, headers=KEY)
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert (body["created"], body["updated"]) == (1, 0)
    assert [item["row"] for item in body["problems"]] == [3, 4, 5]
    again = {"upload": ("商品.csv", "code,name,price\nA-1,甲二,13.00\n".encode(), "text/csv")}
    second = client.post("/api/v1/products/import", files=again, headers=KEY).json()
    assert (second["created"], second["updated"], second["problems"]) == (0, 1, [])
    history = client.get("/api/system/changes?table=product_catalog_items", headers=KEY).json()
    assert {item["field"] for item in history["items"]} == {"name", "price"}


# R-03：缺少必需的列、没有写权限都被拒绝。
def test_import_rejects_bad_file_and_reader(client: TestClient) -> None:
    missing = {"upload": ("a.csv", "名称,单价\n甲,1\n".encode(), "text/csv")}
    reply = client.post("/api/v1/products/import", files=missing, headers=KEY)
    assert reply.status_code == 422 and "编码" in reply.json()["message"]
    upload = {"upload": ("a.csv", CSV.encode(), "text/csv")}
    assert client.post("/api/v1/products/import", files=upload, headers=READER).status_code == 403


# R-04：导出 Excel，列与导入相同；导出的文件再导入时全部是修改，没有问题行。
def test_export_xlsx_round_trip(client: TestClient) -> None:
    for code in ("B-1", "A-1"):
        client.post(
            "/api/v1/products", json={"code": code, "name": code, "price": "1.00"}, headers=KEY
        )
    exported = client.get("/api/v1/products/export?format=xlsx", headers=READER)
    assert exported.status_code == 200
    sheet = load_workbook(io.BytesIO(exported.content)).worksheets[0]
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    assert rows == [
        ["编码", "名称", "单价", "在售"],
        ["A-1", "A-1", "1.00", "是"],
        ["B-1", "B-1", "1.00", "是"],
    ]
    upload = {"upload": ("products.xlsx", exported.content, "application/octet-stream")}
    result = client.post("/api/v1/products/import", files=upload, headers=KEY).json()
    assert (result["created"], result["updated"], result["problems"]) == (0, 2, [])
