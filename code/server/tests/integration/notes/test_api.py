"""
验证完整 HTTP 流程与常见失败情况。
覆盖持久化、事务回滚、权限、校验和健康检查。
"""

from fastapi.testclient import TestClient

from app.setup.app import create_app
from shared.config.settings import Settings
from shared.db.connect import connect
from shared.db.migrate import migrate

KEY = {"X-API-Key": "test-key"}


# 验证创建、分页、读取、更新和删除的完整流程。
def test_note_flow(client: TestClient) -> None:
    response = client.post("/api/v1/notes", json={"title": " 第一条 "}, headers=KEY)
    assert response.status_code == 201
    note = response.json()
    assert note["title"] == "第一条"
    path = f"/api/v1/notes/{note['id']}"
    assert client.get(path).json() == note
    page = client.get("/api/v1/notes?limit=1").json()
    assert page["total"] == 1
    assert page["items"] == [note]
    response = client.put(path, json={"title": "已修改", "body": "正文"}, headers=KEY)
    assert response.status_code == 200
    assert response.json()["created_at"] == note["created_at"]
    assert client.delete(path, headers=KEY).status_code == 204
    assert client.get(path).status_code == 404


# 验证重复标题不会覆盖原数据或留下部分更新。
def test_conflict_rolls_back(client: TestClient) -> None:
    first = client.post("/api/v1/notes", json={"title": "甲"}, headers=KEY).json()
    second = client.post("/api/v1/notes", json={"title": "乙"}, headers=KEY).json()
    response = client.put(
        f"/api/v1/notes/{second['id']}", json={"title": "甲", "body": "不应保存"}, headers=KEY
    )
    assert response.status_code == 409
    assert response.json()["code"] == "title_used"
    assert client.get(f"/api/v1/notes/{second['id']}").json() == second
    assert client.get(f"/api/v1/notes/{first['id']}").json() == first
    assert client.post("/api/v1/notes", json={"title": "甲"}, headers=KEY).status_code == 409
    assert client.get("/api/v1/notes").json()["total"] == 2


# 验证错误密钥与缺少密钥均不能写入。
def test_write_access(client: TestClient) -> None:
    for headers in ({}, {"X-API-Key": "wrong"}):
        response = client.post("/api/v1/notes", json={"title": "拒绝"}, headers=headers)
        assert response.status_code == 401
    assert client.get("/api/v1/notes").json()["total"] == 0


# 验证参数错误统一返回且不泄露提交内容。
def test_validation(client: TestClient) -> None:
    for data in ({"title": "  "}, {"title": "有效", "unknown": "private"}):
        response = client.post("/api/v1/notes", json=data, headers=KEY)
        assert response.status_code == 422
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
        assert "private" not in response.text
    assert client.get("/api/v1/notes?limit=101").status_code == 422
    assert client.get("/api/v1/notes/-1").status_code == 422


# 验证未知接口也遵守统一错误格式。
def test_unknown_route(client: TestClient) -> None:
    response = client.get("/missing")
    assert response.status_code == 404
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


# 验证未初始化时保持存活但不报告数据库就绪。
def test_uninitialized(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.get("/api/v1/notes").status_code == 503
    assert not settings.db_path.exists()


# 验证重复迁移不丢失数据且重启后仍能读取。
def test_persistence(client: TestClient, settings: Settings) -> None:
    client.post("/api/v1/notes", json={"title": "保留"}, headers=KEY)
    migrate(settings.db_path)
    with TestClient(create_app(settings)) as other:
        assert other.get("/api/v1/notes").json()["items"][0]["title"] == "保留"
        assert other.get("/health/ready").status_code == 200


# 验证没有配置密钥时明确关闭写入。
def test_missing_key(settings: Settings) -> None:
    settings.write_key = None
    migrate(settings.db_path)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/notes", json={"title": "拒绝"})
        assert response.status_code == 503


# 验证事务中途异常会回滚已经执行的写入。
def test_transaction_rollback(settings: Settings) -> None:
    migrate(settings.db_path)
    conn = connect(settings.db_path)
    try:
        try:
            with conn:
                conn.execute(
                    "INSERT INTO notes (title, body, created_at) VALUES (?, ?, ?)",
                    ("回滚", "", "2026-01-01T00:00:00+00:00"),
                )
                raise RuntimeError("模拟后续步骤失败")
        except RuntimeError:
            pass
        assert conn.execute("SELECT count(*) FROM notes").fetchone()[0] == 0
    finally:
        conn.close()
