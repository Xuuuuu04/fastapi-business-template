import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from shared.access.keys import ApiKeyConfig, hash_key
from tests.framework.pipeline_sample import module
from tests.framework.test_pipelines import start
from tests.testing_app import make_settings, prepare_test_database_now


@pytest.fixture
def pipeline_client(tmp_path: Path):
    settings = make_settings(
        tmp_path,
        api_keys=[
            ApiKeyConfig(
                name="manager",
                key_sha256=hash_key("pipeline-manager"),
                permissions=["*"],
                org_id="org-a",
            ),
            ApiKeyConfig(
                name="viewer",
                key_sha256=hash_key("pipeline-viewer"),
                permissions=["system.diagnostics"],
                org_id="org-a",
            ),
            ApiKeyConfig(
                name="other",
                key_sha256=hash_key("pipeline-other"),
                permissions=["system.*"],
                org_id="org-b",
            ),
        ],
    )
    prepare_test_database_now(settings.database_url)
    services = build(settings, modules=[replace(module, schedules=())])
    run_id = asyncio.run(start(services, "api"))
    with TestClient(create_app(settings, services)) as client:
        yield client, run_id


def test_pipeline_api_permissions(pipeline_client) -> None:
    client, run_id = pipeline_client
    url = f"/api/system/pipelines/{run_id}"
    viewer = {"X-API-Key": "pipeline-viewer"}
    other = {"X-API-Key": "pipeline-other"}
    assert client.get(url, headers=viewer).status_code == 200
    assert client.post(url + "/resume", json={}, headers=viewer).status_code == 403
    assert client.get(url, headers=other).status_code == 404
    assert client.post(url + "/resume", json={}, headers=other).status_code == 404
    assert client.get("/api/system/pipelines", headers=other).json()["items"] == []


def test_pipeline_api_state_and_summary(pipeline_client) -> None:
    client, run_id = pipeline_client
    headers = {"X-API-Key": "pipeline-manager"}
    data = client.get(f"/api/system/pipelines/{run_id}", headers=headers).json()
    assert data["state"] == "running" and data["stages"][0]["elapsed_ms"] is None
    assert len(data["stages"]) == 4
    assert [stage["state"] for stage in data["stages"][1:]] == ["not_started"] * 3
    assert "input_json" not in data and "caller_json" not in data
    response = client.post(f"/api/system/pipelines/{run_id}/resume", json={}, headers=headers)
    assert response.status_code == 422
