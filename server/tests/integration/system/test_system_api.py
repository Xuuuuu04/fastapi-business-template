import asyncio
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.testing_app import KEY, READER


def test_health(sample_client: TestClient) -> None:
    assert sample_client.get("/health/live").json() == {"status": "ok"}
    ready = sample_client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"


def test_ready_needs_migration(sample_client: TestClient) -> None:
    state = cast(Any, sample_client.app).state
    asyncio.run(set_version(state.settings.database_url, "old"))
    ready = sample_client.get("/health/ready")
    assert ready.status_code == 503 and "请先执行迁移" in ready.json()["problems"][0]


async def set_version(url: str, version: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE alembic_version SET version_num = :v"), {"v": version}
        )
    await engine.dispose()


def test_modules(sample_client: TestClient) -> None:
    body = sample_client.get("/api/system/modules", headers=KEY).json()
    assert [module["name"] for module in body["modules"]] == ["sample_calc", "sample_outer"]
    assert body["links"]["sample_outer"] == {"sample_calc": ["示例计算"]}
    assert "flowchart LR" in body["graph"]


def test_flow_and_field(sample_client: TestClient) -> None:
    flow = sample_client.get("/api/system/flows/sample_calc.calc", headers=KEY).json()
    assert "4. 整理结果" in flow["graph"] and "（计算）" not in flow["graph"]
    field = sample_client.get("/api/system/fields/sample_calc.calc/total", headers=KEY).json()
    assert field["explain"][0].startswith("- 应付（total）：由步骤“计算应付”写入")
    missing = sample_client.get("/api/system/fields/sample_calc.calc/nope", headers=KEY)
    assert missing.status_code == 404


def test_runs_list(sample_client: TestClient) -> None:
    sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY)
    body = sample_client.get("/api/system/runs?module=sample_calc", headers=KEY).json()
    assert body["items"][0]["summary"].startswith("“示例计算”已完成")
    assert body["records"]["note"] == "记录完整"
    assert sample_client.get("/api/system/runs/unknown", headers=KEY).status_code == 404


def test_failed_run_detail(sample_client: TestClient) -> None:
    reply = sample_client.post("/test/calc", json={"amount": "5", "fail_at": "total"}, headers=KEY)
    run_id = reply.json()["run_id"]
    assert reply.status_code == 500 and reply.headers["x-run-id"] == run_id
    detail = sample_client.get(f"/api/system/runs/{run_id}", headers=KEY).json()
    assert "在“计算应付”步骤停止" in detail["summary"] and "flowchart TD" in detail["graph"]


def test_runtime(sample_client: TestClient) -> None:
    body = sample_client.get("/api/system/runtime", headers=KEY).json()
    assert body["memory_mb"] > 0 and "Pool size" in body["database_pool"] and body["jobs"] == {}
    assert body["breakers"] == {"model": "正常"}


def test_stats_and_console(sample_client: TestClient) -> None:
    assert sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY).status_code == 200
    failed = sample_client.post("/test/calc", json={"amount": "5", "fail_at": "busy"}, headers=KEY)
    assert failed.status_code == 503
    rows = sample_client.get("/api/system/stats?module=sample_calc", headers=KEY).json()["items"]
    assert {(row["status"], row["count"]) for row in rows} == {("ok", 1), ("failed", 1)}
    page = sample_client.get("/system/console")
    assert page.status_code == 200 and "模块与运行" in page.text
    assert sample_client.get("/system/console.js").status_code == 200
    assert sample_client.get("/api/system/stats").status_code == 401


def test_security_headers_and_rate_limit(sample_client: TestClient) -> None:
    sample_client.app.state.settings.request_rate_per_minute = 2
    for _ in range(2):
        reply = sample_client.get("/api/system/modules", headers=KEY)
        assert reply.status_code == 200
        assert reply.headers["x-content-type-options"] == "nosniff"
        assert reply.headers["x-frame-options"] == "DENY"
        assert reply.headers["cache-control"] == "no-store"
    limited = sample_client.get("/api/system/modules", headers=KEY)
    assert limited.status_code == 429


def test_diagnostics_need_permission(sample_client: TestClient) -> None:
    assert sample_client.get("/api/system/modules").status_code == 401
    assert sample_client.get("/api/system/modules", headers=READER).status_code == 403


def test_unknown_route(sample_client: TestClient) -> None:
    reply = sample_client.get("/api/v9/nothing")
    assert reply.status_code == 404 and reply.json()["code"] == "route_not_found"


def test_openapi(sample_client: TestClient) -> None:
    schema = sample_client.get("/openapi.json").json()
    operations = [item for path in schema["paths"].values() for item in path.values()]
    assert all(item.get("operationId") and item.get("summary") for item in operations)
    fields = schema["components"]["schemas"]["CalcInput"]["properties"]
    assert fields["amount"]["description"] == "金额；单位：元"


class BrokenCache:
    async def get(self, key: str) -> str | None:
        raise ConnectionError("cache down")


def test_ready_needs_cache(sample_client: TestClient) -> None:
    services = cast(Any, sample_client.app).state.services
    working, services.cache = services.cache, BrokenCache()
    try:
        ready = sample_client.get("/health/ready")
    finally:
        services.cache = working
    assert ready.status_code == 503 and "缓存服务不可用" in ready.json()["problems"][0]


def test_response_ids_can_open_the_run_report(sample_client: TestClient) -> None:
    for failure, status in (("", 200), ("busy", 503), ("total", 500)):
        reply = sample_client.post(
            "/test/calc", json={"amount": "5", "fail_at": failure}, headers=KEY
        )
        assert reply.status_code == status
        assert len(reply.headers.get_list("X-Request-ID")) == 1
        assert len(reply.headers.get_list("X-Run-ID")) == 1
        run_id = reply.headers["X-Run-ID"]
        if status != 200:
            assert reply.json()["run_id"] == run_id
        report = sample_client.get(f"/api/system/runs/{run_id}/report", headers=KEY)
        assert report.status_code == 200
