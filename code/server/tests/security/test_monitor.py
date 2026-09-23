"""
检查监控密钥隔离和敏感数据保护。
业务写入权限不包含运行监控读取权限。
"""

import json

from fastapi.testclient import TestClient


# 验证业务密钥和空凭据不能访问监控。
def test_monitor_access(client: TestClient) -> None:
    for headers in [{}, {"X-API-Key": "test-key"}, {"X-Monitor-Key": "test-key"}]:
        assert client.get("/api/v1/monitor/traces", headers=headers).status_code == 401
    assert (
        client.get(
            "/api/v1/monitor/traces", headers={"X-Monitor-Key": "monitor-key"}
        ).status_code
        == 200
    )


# 验证记录中不保存正文、标题和凭据。
def test_no_payload(client: TestClient) -> None:
    reply = client.post(
        "/api/v1/notes",
        headers={"X-API-Key": "test-key"},
        json={"title": "私密标题", "body": "私密正文"},
    )
    assert reply.status_code == 201
    text = json.dumps(client.app.state.monitor.snapshot(), ensure_ascii=False)
    for secret in ["私密标题", "私密正文", "test-key", "monitor-key"]:
        assert secret not in text


# 验证未配置监控凭据时拒绝开放查询。
def test_monitor_unconfigured(client: TestClient) -> None:
    client.app.state.settings.monitor_key = None
    assert client.get("/api/v1/monitor/traces").status_code == 503


# 验证监控开关关闭时业务仍成功且不新增调用记录。
def test_monitor_off(client: TestClient) -> None:
    client.app.state.monitor.enabled = False
    reply = client.post(
        "/api/v1/notes", headers={"X-API-Key": "test-key"},
        json={"title": "关闭记录", "body": ""},
    )
    assert reply.status_code == 201
    assert client.app.state.monitor.snapshot()["items"] == []
