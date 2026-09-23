"""
验证 HTTP 请求、注册入口、规则和存储的完整调用关系。
监控查询使用独立权限并返回可识别的不完整标记。
"""

from fastapi.testclient import TestClient

HEADERS = {"X-Monitor-Key": "monitor-key"}


# 验证创建请求中的各层调用及静态、实际调用图。
def test_flow(client: TestClient) -> None:
    reply = client.post(
        "/api/v1/notes",
        headers={"X-API-Key": "test-key"},
        json={"title": "调用测试", "body": "正文"},
    )
    assert reply.status_code == 201
    trace = reply.headers["X-Request-ID"]
    data = client.get(
        "/api/v1/monitor/traces", headers=HEADERS, params={"request_id": trace}
    ).json()
    rows = data["items"]
    assert {(row["module"], row["action"]) for row in rows} == {
        ("notes", "create"),
        ("note_rules", "clean"),
        ("note_store", "transaction"),
        ("note_store", "create"),
    }
    assert all(row["status"] == "ok" for row in rows)
    assert all(row["request_id"] == trace for row in rows)
    assert rows[1]["parent_id"] == rows[0]["id"]
    assert rows[3]["parent_id"] == rows[2]["id"]
    assert client.get("/api/v1/monitor/modules", headers=HEADERS).status_code == 200
    declared = client.get("/api/v1/monitor/graph", headers=HEADERS).json()
    assert "notes --> note_store" in declared["mermaid"]
    observed = client.get(
        "/api/v1/monitor/graph", headers=HEADERS, params={"request_id": trace}
    ).json()
    assert observed["count"] == 4
    assert not observed["limited"]
    assert "notes.create" in observed["mermaid"]


# 验证业务冲突会沿调用层级记录，且不破坏已有数据。
def test_failed_flow(client: TestClient) -> None:
    for expected in [201, 409]:
        reply = client.post(
            "/api/v1/notes",
            headers={"X-API-Key": "test-key"},
            json={"title": "同一标题", "body": ""},
        )
        assert reply.status_code == expected
    rows = client.app.state.monitor.snapshot(reply.headers["X-Request-ID"])["items"]
    errors = [row for row in rows if row["status"] == "error"]
    assert {row["action"] for row in errors} == {"create", "transaction"}
    assert client.get("/api/v1/notes").json()["total"] == 1
