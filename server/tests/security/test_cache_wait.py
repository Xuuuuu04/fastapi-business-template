"""
必需缓存有连接与操作总期限，认证不能在缓存故障时放行。
"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.setup.build import build
from app.setup.web import create_app
from shared.cache.backends import RedisCache
from shared.errors.framework import CacheUnavailable
from tests.testing_app import KEY, make_settings, reset_database_now


# 卡住的读写与计数在总期限后取消，连接预算也明确有限。
@pytest.mark.anyio
@pytest.mark.parametrize("method", ["get", "incr"])
async def test_redis_operation_timeout(method: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = RedisCache("redis://127.0.0.1:16389/15", timeout=0.02, max_connections=2)
    cancelled = asyncio.Event()

    # 合成 Redis 客户端一直等待，不建立实际网络连接。
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


# 真实 HTTP 认证与就绪检查遇到不可用缓存都返回 503，不进入允许路径。
def test_unavailable_cache_refuses_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path)
    reset_database_now(settings.database_url)
    services = build(settings, modules=[])
    cache = RedisCache("redis://127.0.0.1:16389/15", timeout=0.02)

    # 模拟缓存服务不回应，以总期限决定失败。
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
