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
    assert "4. 整理结果（计算）" in flow["graph"] and flow["doc"] == "doc/sample_calc"
    field = sample_client.get("/api/system/fields/sample_calc.calc/total", headers=KEY).json()
    assert field["explain"][0].startswith("- 应付（total）：由步骤「计算应付」写入")
    missing = sample_client.get("/api/system/fields/sample_calc.calc/nope", headers=KEY)
    assert missing.status_code == 404


# 运行记录列表带中文摘要和记录完整性说明。
def test_runs_list(sample_client: TestClient) -> None:
    sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY)
    body = sample_client.get("/api/system/runs?module=sample_calc", headers=KEY).json()
    assert body["items"][0]["summary"].startswith("「示例计算」已完成")
    assert body["records"]["note"] == "记录完整"
    assert sample_client.get("/api/system/runs/unknown", headers=KEY).status_code == 404


# 失败的运行：响应带运行编号，诊断接口说明停在哪一步。
def test_failed_run_detail(sample_client: TestClient) -> None:
    reply = sample_client.post("/test/calc", json={"amount": "5", "fail_at": "total"}, headers=KEY)
    run_id = reply.json()["run_id"]
    assert reply.status_code == 500 and reply.headers["x-run-id"] == run_id
    detail = sample_client.get(f"/api/system/runs/{run_id}", headers=KEY).json()
    assert "在「计算应付」步骤停止" in detail["summary"] and "flowchart TD" in detail["graph"]


# 进程状态包含内存、连接池、运行记录和任务数量。
def test_runtime(sample_client: TestClient) -> None:
    body = sample_client.get("/api/system/runtime", headers=KEY).json()
    assert body["memory_mb"] > 0 and "Pool size" in body["database_pool"] and body["jobs"] == {}


# 运行统计按操作和状态汇总，诊断网页只读取受权限保护的系统接口。
def test_stats_and_console(sample_client: TestClient) -> None:
    assert sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY).status_code == 200
    failed = sample_client.post("/test/calc", json={"amount": "5", "fail_at": "busy"}, headers=KEY)
    assert failed.status_code == 503
    rows = sample_client.get("/api/system/stats?module=sample_calc", headers=KEY).json()["items"]
    assert {(row["status"], row["count"]) for row in rows} == {("ok", 1), ("failed", 1)}
    page = sample_client.get("/system/console")
    assert page.status_code == 200 and "运行诊断" in page.text
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


# 诊断接口需要 system.diagnostics 权限。
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
