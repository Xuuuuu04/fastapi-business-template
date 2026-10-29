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


def test_jwt_token_mode_is_explicit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    prepare_test_database_now(settings.database_url)
    built = build(settings, modules=[replace(module, identity_token="jwt")])
    token, _ = issue_token(
        DEVELOPER,
        settings.jwt_secret.get_secret_value(),
        settings.jwt_issuer,
        settings.jwt_audience,
        15,
    )
    with TestClient(create_app(settings, built)) as client:
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer opaque-valid"}
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/system/modules", headers={"X-Legacy-Token": "opaque-valid"}
            ).status_code
            == 200
        )


def test_opaque_failures_are_rate_limited_even_with_dots(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, request_rate_per_minute=2)
    prepare_test_database_now(settings.database_url)
    built = build(settings, modules=[module])
    with TestClient(create_app(settings, built)) as client:
        for _ in range(2):
            assert (
                client.get(
                    "/api/system/modules", headers={"Authorization": "Bearer wrong.two.dots"}
                ).status_code
                == 401
            )
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer wrong.two.dots"}
            ).status_code
            == 429
        )


def test_identity_success_is_not_recorded_but_failure_is(tmp_path: Path) -> None:
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
        assert not built.recorder.store.rows
        assert (
            client.get(
                "/api/system/modules", headers={"Authorization": "Bearer revoked"}
            ).status_code
            == 401
        )
        records = list(built.recorder.store.rows.values())
        assert len(records) == 1 and records[0].status == "failed"
