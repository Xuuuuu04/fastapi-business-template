"""
关闭业务模块后，其接口和接口文档同时移除，系统接口仍可使用。
"""

import pytest
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from shared.config.settings import Settings
from tests.testing_app import KEY


# 关闭全部业务模块时，不暴露任何模块接口。
def test_empty_catalog_keeps_only_system_routes(settings: Settings) -> None:
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/health/live" in paths
        assert not any(path.startswith(("/api/v1/files", "/api/v1/access")) for path in paths)
        assert client.get("/api/v1/files/north", headers=KEY).status_code == 404
        assert client.get("/health/live").status_code == 200


# 关闭一个模块不影响其他模块的接口；用户权限的两个接口文件一起关闭。
@pytest.mark.parametrize("disabled", ["file_library", "user_access"])
def test_disabled_module_routes_disappear(settings: Settings, disabled: str) -> None:
    settings.disabled_modules = [disabled]
    with TestClient(create_app(settings)) as client:
        paths = client.get("/openapi.json").json()["paths"]
        prefix = "/api/v1/files" if disabled == "file_library" else "/api/v1/access"
        assert not any(path.startswith(prefix) for path in paths)
        other = "/api/v1/access" if disabled == "file_library" else "/api/v1/files"
        assert any(path.startswith(other) for path in paths)


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
        build(settings)
