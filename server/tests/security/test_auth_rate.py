from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from tests.testing_app import KEY, make_settings, reset_database_now


@pytest.mark.parametrize(
    "headers",
    [
        {"X-API-Key": "invalid"},
        {"Authorization": "Bearer invalid.jwt.token"},
    ],
)
def test_invalid_credentials_share_source_limit(tmp_path: Path, headers: dict[str, str]) -> None:
    settings = make_settings(tmp_path, request_rate_per_minute=2)
    reset_database_now(settings.database_url)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        statuses = [
            client.get("/api/system/modules", headers=headers).status_code for _ in range(3)
        ]
        assert statuses == [401, 401, 429]
        assert client.get("/api/system/modules", headers=KEY).status_code == 200


def test_rotating_invalid_credentials_does_not_create_new_buckets(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, request_rate_per_minute=1)
    reset_database_now(settings.database_url)
    with TestClient(create_app(settings, build(settings, modules=[]))) as client:
        assert client.get("/api/system/modules", headers={"X-API-Key": "first"}).status_code == 401
        assert (
            client.get("/api/system/modules", headers={"Authorization": "Bearer other"}).status_code
            == 429
        )
