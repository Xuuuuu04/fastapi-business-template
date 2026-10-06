"""
关闭业务模块后，其接口和接口文档同时移除，系统接口仍可使用。
"""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from shared.config.settings import Settings
from shared.public import Module
from tests.framework.sample_resources import file_module
from tests.framework.sample_routes import sample_router
from tests.testing_app import KEY


# 关闭全部业务模块时，不暴露任何模块接口。
def test_empty_catalog_keeps_only_system_routes(settings: Settings) -> None:
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/health/live" in paths
        assert not any(path.startswith(("/api/v1/files", "/api/v1/access")) for path in paths)
        assert client.get("/api/v1/files/north", headers=KEY).status_code == 404
        assert client.get("/health/live").status_code == 200


# 一个模块的多个接口一起关闭，其他模块与系统接口继续可用。
@pytest.mark.parametrize("disabled", ["sample_calc", "sample_outer"])
def test_disabled_module_routes_disappear(
    settings: Settings, disabled: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_router = APIRouter()
    other_router.add_api_route("/test/outer", lambda: {"ok": True})
    second_router = APIRouter()
    second_router.add_api_route("/test/extra", lambda: {"ok": True})
    modules = [
        Module(name, "接口测试", "1", provides={}) for name in ("sample_calc", "sample_outer")
    ]
    monkeypatch.setattr("app.setup.build.MODULES", modules)
    monkeypatch.setattr(
        "app.api.routers.MODULE_ROUTERS",
        {
            "sample_calc": (sample_router, second_router),
            "sample_outer": (other_router,),
        },
    )
    settings.disabled_modules = [disabled]
    selected = [module for module in modules if module.name != disabled]
    with TestClient(create_app(settings, build(settings, modules=selected))) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert ("/test/calc" in paths) == (disabled != "sample_calc")
        assert ("/test/extra" in paths) == (disabled != "sample_calc")
        assert ("/test/outer" in paths) == (disabled != "sample_outer")
        assert "/health/live" in paths


# 没有文件和大模型需求时，不创建相关服务，也不要求 S3 桶或旧库地址有效。
@pytest.mark.anyio
async def test_unused_services_are_not_created(settings: Settings) -> None:
    settings.file_storage = "s3"
    settings.s3_bucket = ""
    settings.legacy_database_url = "not-a-database-url"
    settings.data_keys = []
    services = build(settings, modules=[])
    try:
        assert services.models is None
        assert services.uploads is None and services.runtime.files is None
        assert services.legacy is None and services.runtime.vault is None
    finally:
        await services.close()


# 启用文件模块时，缺少 S3 桶仍须拒绝启动，不能用空实现掩盖配置错误。
def test_used_file_service_requires_configuration(settings: Settings) -> None:
    from shared.errors.framework import ConfigError

    settings.file_storage = "s3"
    settings.s3_bucket = ""
    with pytest.raises(ConfigError, match="APP_S3_BUCKET"):
        build(settings, modules=[file_module])
