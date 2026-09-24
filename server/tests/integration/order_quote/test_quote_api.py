"""
订单报价的接口测试：从 HTTP 入口创建和读取报价，查看运行诊断报告，受理并执行后台任务。
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine

from app.setup.build import build
from service.order_quote.store.tables import quotes
from shared.config.settings import Settings
from shared.jobs.worker import Worker, WorkerOptions
from shared.model_calls.providers import FakeModel
from tests.testing_app import KEY, READER


# 准备三个商品：A-1 在售有价，B-2 停售，C-3 未定价。
def add_products(client: TestClient) -> None:
    products = [
        {"code": "A-1", "name": "甲", "price": "12.50"},
        {"code": "B-2", "name": "乙", "price": "3.00", "on_sale": False},
        {"code": "C-3", "name": "丙"},
    ]
    for body in products:
        assert client.post("/api/v1/products", json=body, headers=KEY).status_code == 201


# 金卡客户的报价：合并明细、排除不能报价的商品、优惠 10%、保存并能读回；别人看不到（R-07）。
def test_create_and_read_quote(client: TestClient) -> None:
    add_products(client)
    lines = [
        {"code": "a-1", "quantity": 2},
        {"code": "A-1", "quantity": 1},
        {"code": "B-2", "quantity": 1},
        {"code": "C-3", "quantity": 5},
    ]
    reply = client.post(
        "/api/v1/quotes",
        json={"customer": "星河", "member_level": "gold", "lines": lines},
        headers=KEY,
    )
    assert reply.status_code == 201
    quote = reply.json()
    assert (quote["subtotal"], quote["discount"], quote["total"]) == ("37.50", "3.75", "33.75")
    assert quote["excluded"] == ["B-2", "C-3"] and quote["lines"][0]["quantity"] == 3
    again = client.get(f"/api/v1/quotes/{quote['id']}", headers=KEY)
    assert again.status_code == 200 and again.json() == quote
    # R-07：没有 order_quote.manage 权限的调用者看不到别人创建的报价。
    other = client.get(f"/api/v1/quotes/{quote['id']}", headers=READER)
    assert other.status_code == 404 and other.json()["code"] == "quote_missing"


# 所有商品都不能报价时返回 422，写入被撤销。
def test_nothing_to_quote(client: TestClient) -> None:
    reply = client.post(
        "/api/v1/quotes",
        json={"customer": "星河", "member_level": "none", "lines": [{"code": "Z", "quantity": 1}]},
        headers=KEY,
    )
    assert reply.status_code == 422 and reply.json()["code"] == "nothing_to_quote"
    assert client.get("/api/v1/quotes/1", headers=KEY).status_code == 404


# 诊断报告按运行编号给出中文摘要、每一步的规则和位置，以及调用的下一层操作。
def test_run_report(client: TestClient) -> None:
    add_products(client)
    reply = client.post(
        "/api/v1/quotes",
        json={
            "customer": "星河",
            "member_level": "silver",
            "lines": [{"code": "A-1", "quantity": 1}],
        },
        headers=KEY,
    )
    report = client.get(f"/api/system/runs/{reply.headers['x-run-id']}/report", headers=KEY).text
    assert "「创建报价」已完成，执行 8 个步骤" in report
    assert "| 4 | 计算会员优惠 | 计算 | 完成（条件：客户是会员） |" in report
    assert "service/order_quote/steps/quote_rules.py" in report
    assert "## 下一层：查询可报价的单价" in report and "explain_quote" in report


# 失败的运行在报告中指出停在哪一步和原因。
def test_failed_run_report(client: TestClient) -> None:
    reply = client.post(
        "/api/v1/quotes",
        json={"customer": "星河", "member_level": "none", "lines": [{"code": "Z", "quantity": 1}]},
        headers=KEY,
    )
    run_id = reply.json()["run_id"]
    detail = client.get(f"/api/system/runs/{run_id}", headers=KEY).json()
    assert "在「计算金额」步骤停止：所有商品都不能报价" in detail["summary"]
    assert "之后的 5 个步骤没有执行" in detail["summary"]


# 标记过期作为后台任务受理，worker 执行后可以查到结果。
def test_expire_job(client: TestClient, settings: Settings) -> None:
    accepted = client.post(
        "/api/v1/quotes/expire", json={"days": 30}, headers={**KEY, "Idempotency-Key": "daily-1"}
    )
    assert accepted.status_code == 202
    job_url = accepted.json()["status_url"]
    assert client.get(job_url, headers=KEY).json()["state"] == "queued"
    asyncio.run(run_one_job(settings))
    job = client.get(job_url, headers=KEY).json()
    assert job["state"] == "done" and job["result"] == {"expired": 0}


# R-06：创建超过指定天数的有效报价标为过期，新报价不受影响；重复执行结果相同。
def test_expire_old_quotes(client: TestClient, settings: Settings) -> None:
    add_products(client)
    body = {"customer": "星河", "member_level": "none", "lines": [{"code": "A-1", "quantity": 1}]}
    old, new = (client.post("/api/v1/quotes", json=body, headers=KEY).json() for _ in range(2))
    asyncio.run(backdate(settings.database_url, old["id"], days=31))
    counts = []
    for key in ("expire-1", "expire-2"):
        headers = {**KEY, "Idempotency-Key": key}
        job_url = client.post("/api/v1/quotes/expire", json={"days": 30}, headers=headers).json()
        asyncio.run(run_one_job(settings))
        counts.append(client.get(job_url["status_url"], headers=KEY).json()["result"]["expired"])
    assert counts == [1, 0]
    assert client.get(f"/api/v1/quotes/{old['id']}", headers=KEY).json()["status"] == "expired"
    assert client.get(f"/api/v1/quotes/{new['id']}", headers=KEY).json()["status"] == "active"


# 把报价的创建时间改到指定天数之前。
async def backdate(url: str, quote_id: int, days: int) -> None:
    engine = create_async_engine(url)
    moment = datetime.now(UTC) - timedelta(days=days)
    async with engine.begin() as connection:
        await connection.execute(
            update(quotes).where(quotes.c.id == quote_id).values(created_at=moment)
        )
    await engine.dispose()


# 在独立的服务中领取并执行一个任务，模拟 worker 进程。
async def run_one_job(settings: Settings) -> None:
    services = build(settings, provider=FakeModel())
    try:
        worker = Worker(services.runtime, services.queue, settings.api_keys, WorkerOptions())
        ticket = await services.queue.claim(time.time())
        assert ticket is not None
        await worker.execute(ticket)
    finally:
        await services.close()


# 只能查看自己登记的任务。
def test_job_owner_only(client: TestClient) -> None:
    accepted = client.post("/api/v1/quotes/expire", json={"days": 30}, headers=KEY).json()
    assert client.get(accepted["status_url"], headers=READER).status_code == 403


# 结构查询能说明订单报价依赖商品目录、创建报价的 8 个步骤，以及应付金额按 R-04 得出。
def test_quote_structure(client: TestClient) -> None:
    modules = client.get("/api/system/modules", headers=KEY).json()
    assert modules["links"]["order_quote"] == {"product_catalog": ["查询可报价的单价"]}
    flow = client.get("/api/system/flows/order_quote.create_quote", headers=KEY).json()
    assert "8. 整理报价（计算）" in flow["graph"] and flow["doc"] == "doc/order_quote"
    field = client.get("/api/system/fields/order_quote.create_quote/total", headers=KEY).json()
    assert field["explain"][0].startswith(
        "- 应付金额（total）：由步骤「计算应付金额」写入，规则 R-04"
    )
    schema = client.get("/openapi.json").json()["components"]["schemas"]["QuoteRequest"]
    assert schema["properties"]["member_level"]["description"].startswith("会员等级")
