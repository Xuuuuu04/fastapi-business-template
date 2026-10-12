"""
系统接口测试：健康检查、结构查询（模块、流程、字段来源）、运行记录、进程状态、路由不存在、接口文档。
使用只启用测试专用模块的应用，不依赖可删除的示例业务。
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.testing_app import KEY, READER


# 进程存活检查不依赖数据库；就绪检查确认数据库和结构版本。
def test_health(sample_client: TestClient) -> None:
    assert sample_client.get("/health/live").json() == {"status": "ok"}
    ready = sample_client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"


# 数据库结构版本与代码不一致时，就绪检查返回 503 和原因。
def test_ready_needs_migration(sample_client: TestClient) -> None:
    asyncio.run(set_version(sample_client.app.state.settings.database_url, "old"))  # type: ignore[attr-defined]
    ready = sample_client.get("/health/ready")
    assert ready.status_code == 503 and "请先执行迁移" in ready.json()["problems"][0]


# 把数据库记录的迁移版本改成指定值。
async def set_version(url: str, version: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE alembic_version SET version_num = :v"), {"v": version}
        )
    await engine.dispose()


# 模块目录和模块关系图。
def test_modules(sample_client: TestClient) -> None:
    body = sample_client.get("/api/system/modules", headers=KEY).json()
    assert [module["name"] for module in body["modules"]] == ["sample_calc", "sample_outer"]
    assert body["links"]["sample_outer"] == {"sample_calc": ["示例计算"]}
    assert "flowchart LR" in body["graph"]


# 操作的流程图和字段来源；不存在的字段返回 404。
def test_flow_and_field(sample_client: TestClient) -> None:
    flow = sample_client.get("/api/system/flows/sample_calc.calc", headers=KEY).json()
    assert "4. 整理结果" in flow["graph"] and "（计算）" not in flow["graph"]
    assert flow["doc"] == "doc/sample_calc"
    field = sample_client.get("/api/system/fields/sample_calc.calc/total", headers=KEY).json()
    assert field["explain"][0].startswith("- 应付（total）：由步骤“计算应付”写入")
    missing = sample_client.get("/api/system/fields/sample_calc.calc/nope", headers=KEY)
    assert missing.status_code == 404


# 运行记录列表带中文摘要和记录完整性说明。
def test_runs_list(sample_client: TestClient) -> None:
    sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY)
    body = sample_client.get("/api/system/runs?module=sample_calc", headers=KEY).json()
    assert body["items"][0]["summary"].startswith("“示例计算”已完成")
    assert body["records"]["note"] == "记录完整"
    assert sample_client.get("/api/system/runs/unknown", headers=KEY).status_code == 404


# 失败的运行：响应带运行编号，排查接口说明停在哪一步。
def test_failed_run_detail(sample_client: TestClient) -> None:
    reply = sample_client.post("/test/calc", json={"amount": "5", "fail_at": "total"}, headers=KEY)
    run_id = reply.json()["run_id"]
    assert reply.status_code == 500 and reply.headers["x-run-id"] == run_id
    detail = sample_client.get(f"/api/system/runs/{run_id}", headers=KEY).json()
    assert "在“计算应付”步骤停止" in detail["summary"] and "flowchart TD" in detail["graph"]


# 进程状态包含内存、连接池、运行记录、任务数量和连续失败后暂停调用状态。
def test_runtime(sample_client: TestClient) -> None:
    body = sample_client.get("/api/system/runtime", headers=KEY).json()
    assert body["memory_mb"] > 0 and "Pool size" in body["database_pool"] and body["jobs"] == {}
    assert body["breakers"] == {"model": "正常"}


# 运行统计按操作和状态汇总，排查网页只读取受权限保护的系统接口。
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


# 所有响应带浏览器安全头，调用者超出每分钟次数后收到限流错误。
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


# 排查接口需要 system.diagnostics 权限。
def test_diagnostics_need_permission(sample_client: TestClient) -> None:
    assert sample_client.get("/api/system/modules").status_code == 401
    assert sample_client.get("/api/system/modules", headers=READER).status_code == 403


# 不存在的地址返回统一格式的 404。
def test_unknown_route(sample_client: TestClient) -> None:
    reply = sample_client.get("/api/v9/nothing")
    assert reply.status_code == 404 and reply.json()["code"] == "route_not_found"


# 接口文档中每个接口都有操作编号和中文说明。
def test_openapi(sample_client: TestClient) -> None:
    schema = sample_client.get("/openapi.json").json()
    operations = [item for path in schema["paths"].values() for item in path.values()]
    assert all(item.get("operationId") and item.get("summary") for item in operations)
    fields = schema["components"]["schemas"]["CalcInput"]["properties"]
    assert fields["amount"]["description"] == "金额；单位：元"


# 故意连接失败的测试缓存，用来检查故障返回与健康状态。
class BrokenCache:
    # 模拟连不上的 Redis：每次读取都报连接错误。
    async def get(self, key: str) -> str | None:
        raise ConnectionError("cache down")


# 缓存读不到时，就绪检查返回 503，避免把请求转给每次限流都会失败的实例。
def test_ready_needs_cache(sample_client: TestClient) -> None:
    services = sample_client.app.state.services  # type: ignore[attr-defined]
    working, services.cache = services.cache, BrokenCache()
    try:
        ready = sample_client.get("/health/ready")
    finally:
        services.cache = working
    assert ready.status_code == 503 and "缓存服务不可用" in ready.json()["problems"][0]


# 成功、业务错误和程序错误都只返回一个编号，可直接用它查询运行报告。
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
