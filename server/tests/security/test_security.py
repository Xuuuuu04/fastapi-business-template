"""
安全测试：身份与权限、生产配置检查、敏感字段不进入运行记录、错误响应不泄露内部信息、
请求大小和并发限制、请求编号不能被注入内容。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.api.runner import RunDep
from app.setup.build import build
from app.setup.web import create_app
from shared.config.settings import Settings
from shared.errors.framework import ConfigError
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


# 把令牌复制到另一个敏感字段，并在令牌为 boom 时抛出带敏感内容的异常。
@step("核对令牌", reads=["user", "token"], writes=["copied", "result"])
def check_token(data: LoginWork) -> None:
    if data.token == "boom":
        raise ValueError(f"连接失败，密码是 {data.token}")
    data.copied = data.token
    data.result = Checked(user=data.user)


login = contract(
    "secure_demo.login", "核对令牌", input=Login, output=Checked, access="secure_demo.use"
)
secure_module = Module(
    "secure_demo",
    "安全示例",
    "1",
    provides={login: Flow("核对令牌", work=LoginWork, result="result", steps=[check_token])},
)
router = APIRouter()


# 测试用接口：执行核对令牌操作。
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


# 敏感字段的内容不进入运行记录和诊断报告。
def test_secret_values_stay_out_of_records(secure_client: TestClient) -> None:
    reply = secure_client.post(
        "/test/login", json={"user": "amy", "token": "s3cret-token"}, headers=KEY
    )
    assert reply.status_code == 200
    report = secure_client.get(
        f"/api/system/runs/{reply.headers['x-run-id']}/report", headers=KEY
    ).text
    assert "s3cret-token" not in report and "敏感字段，不记录内容" in report


# 程序异常的响应只给编号，不回显异常内容；诊断记录中保留原因供排查。
def test_unexpected_error_is_not_leaked(secure_client: TestClient) -> None:
    reply = secure_client.post("/test/login", json={"user": "amy", "token": "boom"}, headers=KEY)
    body = reply.json()
    assert reply.status_code == 500 and body["code"] == "internal_error"
    assert "boom" not in reply.text and body["run_id"]


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
