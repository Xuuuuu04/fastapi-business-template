import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from shared.cache.backends import RedisCache
from shared.errors.framework import CacheUnavailable
from tests.testing_app import KEY, make_settings, reset_database_now


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["get", "incr"])
async def test_redis_operation_timeout(method: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = RedisCache("redis://127.0.0.1:16389/15", timeout=0.02, max_connections=2)
    cancelled = asyncio.Event()

    async def waiting(*args: object, **kwargs: object) -> str:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return ""

    monkeypatch.setattr(cache.client, "get" if method == "get" else "execute_command", waiting)
    try:
        with pytest.raises(CacheUnavailable):
            await (cache.get("test") if method == "get" else cache.incr("test", 60))
        assert cancelled.is_set() and cache.client.connection_pool.max_connections == 2
        options = cache.client.connection_pool.connection_kwargs
        assert options["socket_timeout"] == options["socket_connect_timeout"] == 0.02
    finally:
        await cache.close()


def test_unavailable_cache_refuses_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path)
    reset_database_now(settings.database_url)
    services = build(settings, modules=[])
    cache = RedisCache("redis://127.0.0.1:16389/15", timeout=0.02)

    async def waiting(*args: object, **kwargs: object) -> str:
        await asyncio.Event().wait()
        return ""

    monkeypatch.setattr(cache.client, "get", waiting)
    monkeypatch.setattr(cache.client, "execute_command", waiting)
    services.cache = cache
    with TestClient(create_app(settings, services)) as client:
        reply = client.get("/api/system/modules", headers=KEY)
        assert reply.status_code == 503 and reply.json()["code"] == "cache_unavailable"
        assert client.get("/health/ready").status_code == 503
