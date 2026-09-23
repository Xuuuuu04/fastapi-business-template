"""
验证 API 文档导出与实际接口一致。
检查离线行为、权限声明和版本比较。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.docs.compare import compare
from app.api.docs.export import export
from app.setup.app import create_app
from shared.config.settings import Settings


# 验证文档导出不创建数据库并覆盖全部十个接口。
def test_export(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "absent" / "app.db"))
    schema = export(tmp_path / "docs")
    assert not (tmp_path / "absent").exists()
    assert sum(len(entries) for entries in schema["paths"].values()) == 10
    assert schema["paths"]["/api/v1/notes"]["post"]["security"] == [{"WriteKey": []}]
    assert not schema["paths"]["/api/v1/notes"]["get"].get("security")
    assert schema["paths"]["/api/v1/notes"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/Error")
    assert "创建笔记" in (tmp_path / "docs/index.md").read_text()
    assert (tmp_path / "docs/openapi.json").exists()


# 验证线上 OpenAPI 与应用生成的文档完全一致。
def test_runtime_schema(client: TestClient) -> None:
    assert client.get("/openapi.json").json() == client.app.openapi()
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


# 验证关闭在线文档后仍可离线生成接口定义。
def test_docs_disabled(settings: Settings) -> None:
    settings.docs = False
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
    assert "/api/v1/notes" in app.openapi()["paths"]


# 验证删除接口和模型变化会出现在审查结果中。
def test_compare() -> None:
    old = {"paths": {"/notes": {"get": {"summary": "读取"}}}, "components": {}}
    new = {"paths": {}, "components": {"schemas": {"Note": {"type": "object"}}}}
    assert compare(old, old) == []
    assert "删除接口：GET /notes" in compare(old, new)
    assert any("共享模型" in item for item in compare(old, new))
