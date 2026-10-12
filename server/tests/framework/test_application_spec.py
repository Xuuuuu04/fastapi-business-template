"""
实际产品组装、隔离配置和额外后台入口必须采用相同声明。
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient
from pydantic import Field

from app.setup.build import build
from app.setup.web import create_app
from shared.application.spec import ApplicationSpec, WorkerSpec
from shared.config.settings import Settings
from shared.errors.framework import ConfigError


# 产品配置的字段与校验继续生效，测试不加载部署环境的取值。
class ProductSettings(Settings):
    tenant_scope: str = Field(default="synthetic", min_length=1)


# 隔离模式既不读取环境中的生产连接，也不读取当前目录的.env。
def test_offline_and_test_settings_ignore_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("APP_ENV=production\nAPP_TENANT_SCOPE=from-file\n")
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql://private.invalid/live")
    monkeypatch.setenv("APP_TENANT_SCOPE", "from-environment")
    spec = ApplicationSpec(name="合成产品", settings_type=ProductSettings)
    for mode in ("offline", "test"):
        settings = spec.settings(mode)
        assert settings.env == "test" and settings.database_url.startswith("sqlite")
        assert settings.tenant_scope == "synthetic" and settings.name == "合成产品"
    assert "private.invalid" not in str(spec.describe())


# 显式传入测试配置仍应用产品约束，而且API与build不会重复应用策略。
def test_api_uses_declared_routes_configuration_and_version(tmp_path) -> None:
    configured = []
    router = APIRouter(prefix="/product")

    # 只返回公开的产品配置效果，不返回配置对象或凭据。
    @router.get("/limits")
    async def limits(request: Request) -> dict:
        return {"max": request.app.state.settings.max_inflight}

    # 产品只把普通请求并发限制收紧，不改模板中间件。
    def configure(settings: Settings) -> Settings:
        configured.append(1)
        settings.max_inflight = 17
        return settings

    spec = ApplicationSpec(
        name="合成产品", version="1.2.3", modules=(), routers=(router,), configure=configure
    )
    settings = spec.settings("test", database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db")
    with TestClient(create_app(settings, application=spec)) as client:
        assert client.get("/product/limits").json() == {"max": 17}
        assert client.app.openapi()["info"]["version"] == "1.2.3"
        assert client.get("/api/system/modules").status_code == 401
    assert configured == [1]


# 离线查看不调用网络适配器；实际本机组装只创建一次声明的模型实现。
@pytest.mark.anyio
async def test_model_factory_is_runtime_only(tmp_path) -> None:
    from shared.model_calls.providers import FakeModel

    factories = []

    # 此提供者仅记录创建次数，不调用模型网络。
    def provider(settings: Settings) -> FakeModel:
        factories.append(settings.env)
        return FakeModel()

    spec = ApplicationSpec(model_provider=provider)
    spec.describe()
    services = build(spec.settings("offline"), modules=[], application=spec)
    await services.close()
    assert factories == []
    services = build(spec.settings("offline", env="local"), modules=[], application=spec)
    await services.close()
    assert factories == ["local"]


# 后台扩展与队列共用停止信号，全部退出后才释放共用服务。
@pytest.mark.anyio
async def test_worker_extension_shares_lifecycle(monkeypatch) -> None:
    from app.setup import worker as entry

    events = []

    # 队列替身仍真实等待停止事件，不访问测试之外的数据库。
    class QueueWorker:
        # 替身不创建真实队列资源。
        def __init__(self, *args) -> None:
            pass

        # 与正式worker一样等待停止信号。
        async def run(self, stop: asyncio.Event) -> None:
            events.append("jobs")
            await stop.wait()

    # 标记共用资源何时关闭。
    async def close() -> None:
        events.append("closed")

    services = SimpleNamespace(
        runtime=None,
        queue=None,
        catalog=SimpleNamespace(digest="sample"),
        close=close,
        recorder=SimpleNamespace(store=SimpleNamespace(immediate=True)),
    )

    # 扩展收到同一服务对象并主动结束此次测试。
    async def extension(bundle, stop: asyncio.Event) -> None:
        assert bundle is services
        events.append("extension")
        stop.set()

    spec = ApplicationSpec(workers=(WorkerSpec("extension", extension),))
    monkeypatch.setattr(entry, "build", lambda *args, **kwargs: services)
    monkeypatch.setattr(entry, "Worker", QueueWorker)
    await entry.serve(spec.settings("test"), application=spec)
    assert events == ["jobs", "extension", "closed"]


# 重复或保留的后台名称不能造成两个循环争用同一入口。
def test_duplicate_workers_are_rejected() -> None:
    # 空循环只用于声明名称校验。
    async def run(services, stop) -> None:
        pass

    spec = ApplicationSpec(workers=(WorkerSpec("jobs", run),))
    with pytest.raises(ConfigError, match="jobs"):
        spec.settings("test")


# 通用测试配置进入产品时补齐产品字段，不以通用Settings绕过产品配置类型。
def test_explicit_settings_are_promoted_to_product_type() -> None:
    spec = ApplicationSpec(settings_type=ProductSettings)
    result = spec.prepare(Settings(_env_file=None, env="test", max_inflight=23))
    assert isinstance(result, ProductSettings) and result.tenant_scope == "synthetic"
    assert result.max_inflight == 23


# 正式权限扩展在测试工厂同样生效，文档与HTTP不会漏掉产品安装步骤。
def test_api_extension_installs_identity_policy(tmp_path) -> None:
    from app.api.identity import get_caller
    from shared.access.caller import Caller

    # 此策略只授予结构查询权限。
    async def identity() -> Caller:
        return Caller("synthetic", "service", "合成身份", frozenset({"system.diagnostics"}))

    # 产品安装的权限依赖也进入测试工厂。
    def install(app) -> None:
        app.dependency_overrides[get_caller] = identity

    spec = ApplicationSpec(modules=(), api_setup=install)
    settings = spec.settings("test", database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db")
    with TestClient(create_app(settings, application=spec)) as client:
        assert client.get("/api/system/modules").status_code == 200
