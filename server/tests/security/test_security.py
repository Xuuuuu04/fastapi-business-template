"""
安全测试：身份与权限、生产配置检查、敏感字段不进入运行记录、错误响应不泄露内部信息、
请求大小和并发限制、请求编号不能被注入内容。
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.api.runner import RunDep
from app.setup.build import build
from app.setup.web import create_app
from shared.access.caller import Caller
from shared.access.tokens import issue_token, verify_token
from shared.config.settings import Settings
from shared.errors.framework import ConfigError, NotSignedIn
from shared.model_calls.providers import FakeModel
from shared.public import Data, Flow, Module, WorkData, contract, meaning, remote, step
from tests.testing_app import KEY, make_settings, reset_database_now

remote_module = Module(
    "sample_partner", "外部系统示例", "1", provides={}, remotes=(remote("partner", "合作方"),)
)


# 敏感字段保护测试接收的账号与令牌。
class Login(Data):
    user: str = meaning("用户名")
    token: str = meaning("访问令牌", secret=True)


# 敏感字段保护测试允许返回的账号信息。
class Checked(Data):
    user: str = meaning("用户名")


# 敏感字段保护测试各步骤共享的令牌和公开结果。
class LoginWork(WorkData):
    user: str = meaning("用户名")
    token: str = meaning("访问令牌", secret=True)
    copied: str = meaning("令牌副本", secret=True)
    result: Checked = meaning("结果")


# 把令牌复制到另一个敏感字段，并在令牌为 boom 时抛出带敏感内容的异常。
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


# 测试用接口：执行检查令牌操作。
@router.post("/test/login")
async def post_login(body: Login, run: RunDep) -> Checked:
    return await run(login, body)


# 带安全示例模块的应用。
@pytest.fixture
def secure_client(settings: Settings) -> Iterator[TestClient]:
    reset_database_now(settings.database_url)
    app = create_app(settings, build(settings, modules=[secure_module], provider=FakeModel()))
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# 错误的服务密钥返回 401，不能当作匿名访问继续。
def test_wrong_key(sample_client: TestClient) -> None:
    reply = sample_client.get("/api/system/modules", headers={"X-API-Key": "guess"})
    assert reply.status_code == 401 and reply.json()["message"] == "服务密钥无效"


# 最外层生成的意外失败也必须带安全与请求追查响应头。
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


# 生产环境拒绝开发者身份、SQLite、内存运行记录和缺少密钥的配置。
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


# 本地开发身份只在 local 环境生效。
def test_dev_caller_only_local(tmp_path: Path) -> None:
    for env, status in (("local", 200), ("test", 401)):
        settings = make_settings(tmp_path, env=env, dev_caller=True)
        reset_database_now(settings.database_url)
        with TestClient(create_app(settings, build(settings, modules=[]))) as client:
            assert client.get("/api/system/modules").status_code == status


# 敏感字段的内容不进入运行记录和排查报告。
def test_secret_values_stay_out_of_records(secure_client: TestClient) -> None:
    reply = secure_client.post(
        "/test/login", json={"user": "amy", "token": "s3cret-token"}, headers=KEY
    )
    assert reply.status_code == 200
    report = secure_client.get(
        f"/api/system/runs/{reply.headers['x-run-id']}/report", headers=KEY
    ).text
    assert "s3cret-token" not in report and "敏感字段，不记录内容" in report


# 程序异常的响应、报告和日志都不回显敏感内容，排查仍有类型与调用位置。
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


# 请求正文超过限制时返回 413。
def test_body_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_body_bytes=1000, upload_paths=["/upload/"])
    reset_database_now(settings.database_url)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        reply = client.post(
            "/health/live", content=b"x" * 2000, headers={"Content-Type": "application/json"}
        )
        assert reply.status_code == 413 and reply.json()["code"] == "request_too_large"
        # 上传路径按上传大小限制，2000 字节不会被拒绝；超过上传限制仍返回 413。
        assert client.post("/upload/x", content=b"x" * 2000).status_code == 404
        limit = settings.upload_max_bytes + 64 * 1024
        assert client.post("/upload/x", content=b"x" * (limit + 1)).status_code == 413


# 同时处理的请求达到上限时返回 503。
def test_inflight_limit(sample_client: TestClient) -> None:
    limits = sample_client.app.state.limits  # type: ignore[attr-defined]
    limits.inflight = limits.max_inflight
    try:
        reply = sample_client.get("/health/live")
    finally:
        limits.inflight = 0
    assert reply.status_code == 503 and reply.json()["code"] == "too_busy"


# 调用方传入的请求编号格式正确时沿用，含有换行等内容时换成新编号。
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


# 没有配置跨域来源时，不返回允许跨域的响应头。
def test_no_cors_by_default(sample_client: TestClient) -> None:
    reply = sample_client.get("/health/live", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in reply.headers


# 更换签名密钥的过渡期内，旧密钥签发的令牌仍能校验；去掉旧密钥后被拒绝。
def test_token_secret_rotation() -> None:
    old, new = "old-secret-" + "x" * 32, "new-secret-" + "y" * 32
    user = Caller("7", "user", "alice", frozenset({"file_library.read"}), "north")
    token, _ = issue_token(user, old, "issuer", "audience", 15)
    assert verify_token(token, [new, old], "issuer", "audience") == user
    with pytest.raises(NotSignedIn):
        verify_token(token, [new], "issuer", "audience")
    with pytest.raises(NotSignedIn):
        verify_token(token, [old], "other-issuer", "audience")


# 已允许的前端可携带登录令牌，其他来源和未允许的请求头仍被拒绝。
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


# 接口文档同时提供服务密钥和登录令牌，调用者可以任选一种身份方式。
def test_api_docs_offer_both_authentication_methods(sample_client: TestClient) -> None:
    schema = sample_client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["服务密钥"]["name"] == "X-API-Key"
    assert schemes["登录令牌"]["scheme"] == "bearer"
    security = schema["paths"]["/api/system/modules"]["get"]["security"]
    assert {"服务密钥": []} in security and {"登录令牌": []} in security
