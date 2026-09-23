"""
商品目录的接口测试：从 HTTP 入口新建、查询、修改、删除商品，检查错误码、权限和运行编号。
"""

from fastapi.testclient import TestClient

from tests.testing_app import KEY, READER


# 新建商品：编码整理成大写，单价按精确小数返回，响应头带运行编号。
def test_create_product(client: TestClient) -> None:
    reply = client.post(
        "/api/v1/products", json={"code": " a-1 ", "name": "打印纸", "price": "12.50"}, headers=KEY
    )
    assert reply.status_code == 201
    body = reply.json()
    assert (body["code"], body["price"], body["on_sale"]) == ("A-1", "12.50", True)
    assert reply.headers["x-run-id"] and reply.headers["x-request-id"]


# 编码重复时返回 409 和稳定的错误码，指出字段。
def test_duplicate_code(client: TestClient) -> None:
    client.post("/api/v1/products", json={"code": "A-1", "name": "甲"}, headers=KEY)
    reply = client.post("/api/v1/products", json={"code": "a-1", "name": "乙"}, headers=KEY)
    assert reply.status_code == 409
    assert reply.json()["code"] == "product_code_used"
    assert reply.json()["fields"] == [{"field": "code", "problem": "编码重复"}]


# 分页查询和在售状态筛选。
def test_list_products(client: TestClient) -> None:
    for code, on_sale in (("A-1", True), ("B-2", False), ("C-3", True)):
        client.post(
            "/api/v1/products", json={"code": code, "name": code, "on_sale": on_sale}, headers=KEY
        )
    page = client.get("/api/v1/products?limit=2", headers=READER).json()
    assert page["total"] == 3 and [item["code"] for item in page["items"]] == ["C-3", "B-2"]
    selling = client.get("/api/v1/products?on_sale=true", headers=READER).json()
    assert [item["code"] for item in selling["items"]] == ["C-3", "A-1"]


# 修改商品和删除商品；删除后读取返回 404。
def test_update_and_delete(client: TestClient) -> None:
    created = client.post(
        "/api/v1/products", json={"code": "A-1", "name": "甲"}, headers=KEY
    ).json()
    path = f"/api/v1/products/{created['id']}"
    changed = client.put(path, json={"code": "A-2", "name": "乙", "price": "3.00"}, headers=KEY)
    assert changed.status_code == 200 and changed.json()["code"] == "A-2"
    assert client.delete(path, headers=KEY).status_code == 204
    missing = client.get(path, headers=KEY)
    assert missing.status_code == 404 and missing.json()["code"] == "product_missing"
    assert client.put(path, json={"code": "A-3", "name": "丙"}, headers=KEY).status_code == 404


# 参数不符合要求时返回 422，逐个字段给出中文说明，不进入业务流程。
def test_invalid_input(client: TestClient) -> None:
    reply = client.post(
        "/api/v1/products",
        json={"code": "", "name": "x", "price": "-1", "color": "red"},
        headers=KEY,
    )
    assert reply.status_code == 422
    body = reply.json()
    assert body["code"] == "invalid_input" and body["run_id"] == ""
    problems = {item["field"]: item["problem"] for item in body["fields"]}
    assert problems == {"code": "文字太短", "price": "数值太小", "color": "不允许出现这个字段"}


# 只读密钥可以查询，不能新建。
def test_reader_cannot_write(client: TestClient) -> None:
    reply = client.post("/api/v1/products", json={"code": "A-1", "name": "甲"}, headers=READER)
    assert reply.status_code == 403 and reply.json()["code"] == "not_allowed"
    assert client.get("/api/v1/products", headers=READER).status_code == 200
