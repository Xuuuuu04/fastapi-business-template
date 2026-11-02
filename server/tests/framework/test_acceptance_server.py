import json
import os
import select
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from fastapi_check.acceptance_environment import isolated_settings, prepare_seed
from fastapi_check.acceptance_server import listen

from app.setup.build import build
from shared.application.spec import ApplicationSpec
from shared.config.settings import Settings
from shared.model_calls.providers import FakeModel

ROOT = Path(__file__).resolve().parents[2]


def test_test_configuration_ignores_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("APP_DATABASE_URL=postgresql://outside.invalid/prod\n")
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql://outside.invalid/prod")
    monkeypatch.setenv("APP_TEST_DATABASE_URL", "postgresql://outside.invalid/test")
    monkeypatch.setenv("APP_CACHE_URL", "redis://outside.invalid")
    settings = isolated_settings(ApplicationSpec(), tmp_path)
    assert settings.database_url == f"sqlite+aiosqlite:///{tmp_path}/acceptance.db"
    assert settings.cache_url == "" and settings.env == "test"


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_url", "sqlite+aiosqlite:///other.db"),
        ("file_root", "/outside"),
        ("env", "production"),
        ("cache_url", "redis://outside.invalid"),
        ("model_base_url", "https://outside.invalid"),
        ("file_storage", "s3"),
        ("otel_endpoint", "https://outside.invalid"),
    ],
)
def test_product_configuration_cannot_escape_isolation(tmp_path, field, value) -> None:
    def configure(settings: Settings) -> Settings:
        setattr(settings, field, value)
        return settings

    spec = ApplicationSpec(configure=configure)
    with pytest.raises(ValueError, match=field):
        isolated_settings(spec, tmp_path)
    assert not (tmp_path / "acceptance.db").exists()


def test_external_factory_is_rejected_before_invocation(tmp_path) -> None:
    calls = []

    def provider(settings: Settings) -> FakeModel:
        calls.append(settings)
        return FakeModel()

    with pytest.raises(ValueError, match="模型工厂"):
        isolated_settings(ApplicationSpec(model_provider=provider), tmp_path)
    assert calls == []


def test_busy_port_is_rejected() -> None:
    with listen(0) as first, pytest.raises(OSError):
        listen(first.getsockname()[1])


@pytest.mark.anyio
async def test_seed_is_explicit_and_rechecks_settings(tmp_path) -> None:
    folder = tmp_path / "runtime"
    folder.mkdir()
    spec = ApplicationSpec(modules=())
    services = build(isolated_settings(spec, folder), modules=[], application=spec)
    try:
        with pytest.raises(ValueError, match="seed.py"):
            await prepare_seed(services, folder, tmp_path)
        seed = tmp_path / "server/tests/acceptance/seed.py"
        seed.parent.mkdir(parents=True)
        seed.write_text(
            "async def prepare(services, folder):\n"
            "    (folder / 'seeded').write_text('synthetic')\n"
        )
        await prepare_seed(services, folder, tmp_path)
        assert (folder / "seeded").read_text() == "synthetic"
        seed.write_text(
            "async def prepare(services, folder):\n"
            "    services.settings.cache_url = 'redis://outside.invalid'\n"
        )
        with pytest.raises(ValueError, match="cache_url"):
            await prepare_seed(services, folder, tmp_path)
    finally:
        await services.close()


def start_server(*extra: str, environment: dict[str, str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "fastapi_dev.main",
            "acceptance-server",
            "--port",
            "0",
            "--run-id",
            "synthetic-check",
            *extra,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )


def starting_record(process: subprocess.Popen) -> dict:
    assert process.stdout is not None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("验收服务提前退出")
        readable, _, _ = select.select([process.stdout], [], [], 0.2)
        if not readable:
            continue
        line = process.stdout.readline()
        if line.startswith("{"):
            record = json.loads(line)
            if record.get("event") == "acceptance_starting":
                return record
    raise AssertionError("验收服务没有报告本轮实例")


def wait_ready(port: int) -> tuple[dict, str | None]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=0.3) as response:
                return json.load(response), response.headers.get("X-Acceptance-Run")
        except (OSError, URLError):
            time.sleep(0.02)
    raise AssertionError("验收 HTTP 服务未就绪")


@pytest.mark.parametrize("termination", [signal.SIGINT, signal.SIGTERM])
def test_real_http_instance_cleans_up_on_interrupt(tmp_path, termination) -> None:
    environment = {
        **os.environ,
        "TMPDIR": str(tmp_path),
        "APP_DATABASE_URL": "postgresql://outside.invalid/production",
    }
    lifecycle = tmp_path / "lifecycle.json"
    process = start_server("--lifecycle-file", str(lifecycle), environment=environment)
    folder = None
    port = None
    try:
        record = starting_record(process)
        folder, port = Path(record["folder"]), record["port"]
        assert json.loads(lifecycle.read_text()) == {
            "run_id": "synthetic-check",
            "folder": str(folder),
            "phase": "created",
        }
        assert folder.is_relative_to(tmp_path) and (folder / "acceptance.db").exists()
        body, identity = wait_ready(port)
        assert body["status"] == "ready" and identity == "synthetic-check"
        with urlopen(f"http://127.0.0.1:{port}/openapi.json") as response:
            assert json.load(response)["info"]["title"]
            assert response.headers["X-Acceptance-Run"] == "synthetic-check"
    finally:
        process.send_signal(termination)
        process.communicate(timeout=10)
    assert folder is not None and not folder.exists()
    assert json.loads(lifecycle.read_text()) == {
        "run_id": "synthetic-check",
        "folder": str(folder),
        "phase": "cleanup_complete",
    }
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_seed_startup_failure_removes_temporary_data(tmp_path) -> None:
    environment = {**os.environ, "TMPDIR": str(tmp_path)}
    lifecycle = tmp_path / "lifecycle.json"
    process = start_server("--seed", "--lifecycle-file", str(lifecycle), environment=environment)
    _, error = process.communicate(timeout=20)
    assert process.returncode != 0 and "验收服务启动失败" in error
    assert list(tmp_path.glob("fastapi-acceptance-*")) == []
    assert json.loads(lifecycle.read_text())["phase"] == "cleanup_complete"


def test_busy_port_does_not_create_temporary_data(tmp_path) -> None:
    environment = {**os.environ, "TMPDIR": str(tmp_path)}
    with listen(0) as first:
        process = start_server("--port", str(first.getsockname()[1]), environment=environment)
        _, error = process.communicate(timeout=10)
        assert process.returncode != 0 and "验收服务启动失败" in error
    assert list(tmp_path.glob("fastapi-acceptance-*")) == []
