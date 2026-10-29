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


class ProductSettings(Settings):
    tenant_scope: str = Field(default="synthetic", min_length=1)


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


def test_api_uses_declared_routes_configuration_and_version(tmp_path) -> None:
    configured = []
    router = APIRouter(prefix="/product")

    @router.get("/limits")
    async def limits(request: Request) -> dict:
        return {"max": request.app.state.settings.max_inflight}

    def configure(settings: Settings) -> Settings:
        configured.append(1)
        settings.max_inflight = 17
        return settings

    spec = ApplicationSpec(
        name="合成产品", version="1.2.3", modules=(), routers=(router,), configure=configure
    )
    settings = spec.settings("test", database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db")
    services = build(settings, modules=[], application=spec)
    with TestClient(create_app(settings, services, application=spec)) as client:
        assert client.get("/product/limits").json() == {"max": 17}
        assert client.app.openapi()["info"]["version"] == "1.2.3"
        assert client.get("/api/system/modules").status_code == 401
    assert configured == [1]


@pytest.mark.anyio
async def test_model_factory_is_runtime_only(tmp_path) -> None:
    from shared.model_calls.providers import FakeModel

    factories = []

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


@pytest.mark.anyio
async def test_worker_extension_shares_lifecycle(monkeypatch) -> None:
    from app.setup import worker as entry

    events = []

    class QueueWorker:
        def __init__(self, *args) -> None:
            pass

        async def run(self, stop: asyncio.Event) -> None:
            events.append("jobs")
            await stop.wait()

    async def close() -> None:
        events.append("closed")

    services = SimpleNamespace(
        runtime=None,
        queue=None,
        catalog=SimpleNamespace(digest="sample"),
        close=close,
        recorder=SimpleNamespace(store=SimpleNamespace(immediate=True)),
    )

    async def extension(bundle, stop: asyncio.Event) -> None:
        assert bundle is services
        events.append("extension")
        stop.set()

    spec = ApplicationSpec(workers=(WorkerSpec("extension", extension),))
    monkeypatch.setattr(entry, "build", lambda *args, **kwargs: services)
    monkeypatch.setattr(entry, "Worker", QueueWorker)
    await entry.serve(spec.settings("test"), application=spec)
    assert events == ["jobs", "extension", "closed"]


def test_duplicate_workers_are_rejected() -> None:
    async def run(services, stop) -> None:
        pass

    spec = ApplicationSpec(workers=(WorkerSpec("jobs", run),))
    with pytest.raises(ConfigError, match="jobs"):
        spec.settings("test")


def test_explicit_settings_are_promoted_to_product_type() -> None:
    spec = ApplicationSpec(settings_type=ProductSettings)
    result = spec.prepare(Settings(_env_file=None, env="test", max_inflight=23))
    assert isinstance(result, ProductSettings) and result.tenant_scope == "synthetic"
    assert result.max_inflight == 23


def test_api_extension_installs_identity_policy(tmp_path) -> None:
    from app.api.identity import get_caller
    from shared.access.caller import Caller

    async def identity() -> Caller:
        return Caller("synthetic", "service", "合成身份", frozenset({"system.diagnostics"}))

    def install(app) -> None:
        app.dependency_overrides[get_caller] = identity

    spec = ApplicationSpec(modules=(), api_setup=install)
    settings = spec.settings("test", database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db")
    services = build(settings, modules=[], application=spec)
    with TestClient(create_app(settings, services, application=spec)) as client:
        assert client.get("/api/system/modules").status_code == 200
