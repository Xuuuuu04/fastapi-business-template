import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.api.runner import RunDep
from app.setup.build import build
from app.setup.web import create_app
from shared.access.caller import Caller, caller_from_record
from shared.access.tokens import issue_token, verify_token
from shared.config.settings import Settings
from shared.errors.framework import ConfigError, NotSignedIn
from shared.model_calls.providers import FakeModel
from shared.public import Data, Flow, Module, WorkData, contract, meaning, remote, step
from tests.testing_app import KEY, make_settings, reset_database_now

remote_module = Module(
    "sample_partner", "外部系统示例", "1", provides={}, remotes=(remote("partner", "合作方"),)
)


class Login(Data):
    user: str = meaning("用户名")
    token: str = meaning("访问令牌", secret=True)


class Checked(Data):
    user: str = meaning("用户名")


class LoginWork(WorkData):
    user: str = meaning("用户名")
    token: str = meaning("访问令牌", secret=True)
    copied: str = meaning("令牌副本", secret=True)
    result: Checked = meaning("结果")


@step("检查令牌", reads=["user", "token"], writes=["copied", "result"])
def check_token(data: LoginWork) -> None:
    if data.token == "boom":
        raise ValueError(f"连接失败，密码是 {data.token}")
    data.copied = data.token
    data.result = Checked(user=data.user)


login = contract(
    "secure_demo.login", "检查令牌", input=Login, output=Checked, access="secure_demo.use"
)
secure_module = Module(
    "secure_demo",
    "安全示例",
    "1",
    provides={login: Flow("检查令牌", work=LoginWork, result="result", steps=[check_token])},
)
router = APIRouter()


@router.post("/test/login")
async def post_login(body: Login, run: RunDep) -> Checked:
    return await run(login, body)


@pytest.fixture
def secure_client(settings: Settings) -> Iterator[TestClient]:
    reset_database_now(settings.database_url)
    app = create_app(settings, build(settings, modules=[secure_module], provider=FakeModel()))
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_wrong_key(sample_client: TestClient) -> None:
    reply = sample_client.get("/api/system/modules", headers={"X-API-Key": "guess"})
    assert reply.status_code == 401 and reply.json()["message"] == "服务密钥无效"


def test_unexpected_response_has_security_headers(secure_client: TestClient) -> None:
    reply = secure_client.post(
        "/test/login", json={"user": "测试用户", "token": "boom"}, headers=KEY
    )
    assert reply.status_code == 500
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert reply.headers["x-frame-options"] == "DENY"
    assert reply.headers["referrer-policy"] == "no-referrer"
    assert reply.headers["cache-control"] == "no-store"
    assert reply.headers["x-request-id"] == reply.json()["request_id"]
    assert reply.headers["x-run-id"] == reply.json()["run_id"]


def test_production_settings_are_checked(tmp_path: Path) -> None:
    sqlite = f"sqlite+aiosqlite:///{tmp_path}/prod.db"
    settings = make_settings(
        tmp_path,
        env="production",
        dev_caller=True,
        api_keys=[],
        database_url=sqlite,
        jwt_secret="short-secret",
    )
    with pytest.raises(ConfigError) as caught:
        build(settings, modules=[remote_module])
    text = str(caught.value)
    assert (
        "PostgreSQL" in text
        and "APP_DEV_CALLER" in text
        and "APP_RUN_RECORDS" in text
        and "APP_API_KEYS" in text
        and "APP_JWT_SECRET" in text
        and "partner" in text
    )


def test_dev_caller_only_local(tmp_path: Path) -> None:
    for env, status in (("local", 200), ("test", 401)):
        settings = make_settings(tmp_path, env=env, dev_caller=True)
        reset_database_now(settings.database_url)
        with TestClient(create_app(settings, build(settings, modules=[]))) as client:
            assert client.get("/api/system/modules").status_code == status


def test_secret_values_stay_out_of_records(secure_client: TestClient) -> None:
    reply = secure_client.post(
        "/test/login", json={"user": "amy", "token": "s3cret-token"}, headers=KEY
    )
    assert reply.status_code == 200
    report = secure_client.get(
        f"/api/system/runs/{reply.headers['x-run-id']}/report", headers=KEY
    ).text
    assert "s3cret-token" not in report and "敏感字段，不记录内容" in report


def test_unexpected_error_is_not_leaked(
    secure_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    logger = logging.getLogger("server")
    logger.addHandler(caplog.handler)
    try:
        reply = secure_client.post(
            "/test/login", json={"user": "amy", "token": "boom"}, headers=KEY
        )
        body = reply.json()
        assert reply.status_code == 500 and body["code"] == "internal_error"
        assert "boom" not in reply.text and body["run_id"]
        report = secure_client.get(f"/api/system/runs/{body['run_id']}/report", headers=KEY)
        assert report.status_code == 200 and "boom" not in report.text
        assert "ValueError" in report.text
        assert "boom" not in caplog.text and "check_token" in caplog.text
    finally:
        logger.removeHandler(caplog.handler)


def test_body_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_body_bytes=1000, upload_paths=["/upload/"])
    reset_database_now(settings.database_url)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        reply = client.post(
            "/health/live", content=b"x" * 2000, headers={"Content-Type": "application/json"}
        )
        assert reply.status_code == 413 and reply.json()["code"] == "request_too_large"
        assert client.post("/upload/x", content=b"x" * 2000).status_code == 404
        limit = settings.upload_max_bytes + 64 * 1024
        assert client.post("/upload/x", content=b"x" * (limit + 1)).status_code == 413


def test_inflight_limit(sample_client: TestClient) -> None:
    limits = cast(Any, sample_client.app).state.limits
    limits.inflight = limits.max_inflight
    try:
        reply = sample_client.get("/health/live")
    finally:
        limits.inflight = 0
    assert reply.status_code == 503 and reply.json()["code"] == "too_busy"


def test_request_id_is_sanitized(sample_client: TestClient) -> None:
    client = sample_client
    assert (
        client.get("/health/live", headers={"X-Request-ID": "order-2026-0001"}).headers[
            "x-request-id"
        ]
        == "order-2026-0001"
    )
    replaced = client.get("/health/live", headers={"X-Request-ID": "bad id; drop"}).headers[
        "x-request-id"
    ]
    assert replaced != "bad id; drop" and len(replaced) == 16


def test_no_cors_by_default(sample_client: TestClient) -> None:
    reply = sample_client.get("/health/live", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in reply.headers


def test_token_secret_rotation() -> None:
    old, new = "old-secret-" + "x" * 32, "new-secret-" + "y" * 32
    user = Caller("7", "user", "alice", frozenset({"file_library.read"}), "north")
    token, _ = issue_token(user, old, "issuer", "audience", 15)
    assert verify_token(token, [new, old], "issuer", "audience") == user
    with pytest.raises(NotSignedIn):
        verify_token(token, [new], "issuer", "audience")
    with pytest.raises(NotSignedIn):
        verify_token(token, [old], "other-issuer", "audience")


def test_cors_allows_login_token_only_for_allowed_origin(settings: Settings) -> None:
    settings.cors = ["https://frontend.example"]
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        headers = {
            "Origin": "https://frontend.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
        reply = client.options("/api/system/modules", headers=headers)
        assert reply.status_code == 200
        assert reply.headers["access-control-allow-origin"] == headers["Origin"]
        refused = client.options(
            "/api/system/modules", headers={**headers, "Origin": "https://other.example"}
        )
        assert refused.status_code == 400
        refused = client.options(
            "/api/system/modules", headers={**headers, "Access-Control-Request-Headers": "x-other"}
        )
        assert refused.status_code == 400


def test_api_docs_offer_both_authentication_methods(sample_client: TestClient) -> None:
    schema = sample_client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["服务密钥"]["name"] == "X-API-Key"
    assert schemes["登录令牌"]["scheme"] == "bearer"
    security = schema["paths"]["/api/system/modules"]["get"]["security"]
    assert {"服务密钥": []} in security and {"登录令牌": []} in security


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "robot"},
        {"org_id": None},
        {"permissions": "orders.read"},
        {"extra": "x"},
    ],
)
def test_caller_record_is_strict(change: dict[str, object]) -> None:
    caller = Caller("u1", "user", "用户", frozenset({"orders.read"}), "org")
    record = caller.to_record()
    assert caller_from_record(record) == caller
    with pytest.raises(ValueError):
        caller_from_record({**record, **change})
    del record["org_id"]
    with pytest.raises(ValueError):
        caller_from_record(record)
