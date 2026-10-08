"""
声明式产品登录入口保留JWT校验、无效凭据限流和标准头优先，不导入业务包。
"""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from shared.access.caller import DEVELOPER
from shared.access.tokens import issue_token
from shared.errors.framework import DeclarationError
from shared.modules.catalog import Catalog
from tests.framework.identity_sample import module, resolve
from tests.testing_app import make_settings, prepare_test_database_now


# 不透明令牌和声明的兼容头走同一解析操作，JWT继续原校验。
def test_custom_identity_and_jwt_are_both_verified(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    prepare_test_database_now(settings.database_url)
    built = build(settings, modules=[module])
    with TestClient(create_app(settings, built)) as client:
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer opaque-valid"}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/system/modules", headers={"X-Legacy-Token": "opaque-valid"}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer revoked"}
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/system/modules",
                headers={"Authorization": "Bearer revoked", "X-Legacy-Token": "opaque-valid"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer " + "x" * 65}
            ).status_code
            == 401
        )
        token, _ = issue_token(
            DEVELOPER,
            settings.jwt_secret.get_secret_value(),
            settings.jwt_issuer,
            settings.jwt_audience,
            15,
        )
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 200
        )


# 未声明或者模块关闭时，兼容头不能成为额外登录入口。
def test_identity_header_disappears_without_module(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    prepare_test_database_now(settings.database_url)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        assert (
            client.get(
                "/api/system/modules", headers={"X-Legacy-Token": "opaque-valid"}
            ).status_code
            == 401
        )


# 多入口、标准头覆盖和错误归属在启动时明确拒绝。
@pytest.mark.parametrize("variant", ["duplicate", "header", "owner"])
def test_bad_identity_declaration_is_rejected(variant) -> None:
    if variant == "duplicate":
        modules = [module, replace(module, name="sample_other", provides={}, identity=resolve)]
    elif variant == "header":
        modules = [replace(module, identity_header="Authorization")]
    else:
        modules = [replace(module, provides={})]
    with pytest.raises(DeclarationError):
        Catalog(modules)
