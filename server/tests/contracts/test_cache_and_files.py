import asyncio
import os
import secrets
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from shared.cache.backends import Cache, MemoryCache, RedisCache
from shared.cache.gate import ModuleCache
from shared.errors.framework import FileTooLarge, StepRuleBroken
from shared.files.gate import ModuleFiles
from shared.files.storage import FileStorage, LocalFiles, S3Files, S3Options
from shared.files.uploads import UploadArea
from shared.public import Data, meaning

pytestmark = pytest.mark.anyio


class Price(Data):
    price: int = meaning("价格", unit="分")


@pytest.fixture(params=["memory", "redis"])
async def cache(request: pytest.FixtureRequest) -> AsyncIterator[Cache]:
    url = os.environ.get("APP_TEST_REDIS_URL", "")
    if request.param == "redis" and not url:
        pytest.skip("没有设置 APP_TEST_REDIS_URL")
    backend: Cache = MemoryCache() if request.param == "memory" else RedisCache(url)
    yield backend
    await backend.close()


@pytest.fixture(params=["local", "s3"])
async def storage(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[FileStorage]:
    if request.param == "local":
        yield LocalFiles(tmp_path / "files")
        return
    endpoint = os.environ.get("APP_TEST_S3_ENDPOINT", "")
    if not endpoint:
        pytest.skip("没有设置 APP_TEST_S3_ENDPOINT")
    options = S3Options(
        os.environ.get("APP_TEST_S3_BUCKET", "template-test"),
        endpoint,
        os.environ.get("APP_TEST_S3_REGION", "us-east-1"),
        os.environ.get("APP_TEST_S3_ACCESS_KEY", ""),
        os.environ.get("APP_TEST_S3_SECRET_KEY", ""),
    )
    files = S3Files(options)
    names = [item["Name"] for item in files.client.list_buckets().get("Buckets", [])]
    if options.bucket not in names:
        files.client.create_bucket(Bucket=options.bucket)
    yield files


async def test_cache_basic_rules(cache: Cache) -> None:
    key = f"test:{secrets.token_hex(4)}"
    assert await cache.get(key) is None
    await cache.set(key, "值", 60)
    assert await cache.get(key) == "值"
    await cache.delete(key)
    assert await cache.get(key) is None
    await cache.set(key, "短期", 0.2)
    assert [await cache.incr(f"{key}:n", 0.2) for _ in range(3)] == [1, 2, 3]
    await asyncio.sleep(0.4)
    assert await cache.get(key) is None
    assert await cache.incr(f"{key}:n", 0.2) == 1


async def test_redis_counter_expiry_and_concurrency(cache: Cache) -> None:
    if not isinstance(cache, RedisCache):
        pytest.skip("本项验证 Redis 原子计数")
    key = f"test:{secrets.token_hex(8)}:atomic"
    try:
        await cache.client.set(key, "1", px=1000)
        assert await cache.incr(key, 60) == 2
        assert 0 < await cache.client.pttl(key) <= 1000
        await cache.client.set(key, "5")
        assert await cache.incr(key, 30) == 6
        assert 0 < await cache.client.pttl(key) <= 30_000
        await cache.delete(key)
        counts = await asyncio.gather(*(cache.incr(key, 30) for _ in range(20)))
        assert sorted(counts) == list(range(1, 21))
        assert 0 < await cache.client.pttl(key) <= 30_000
    finally:
        await cache.delete(key)


async def test_module_cache_prefix_and_data(cache: Cache) -> None:
    module = f"m{secrets.token_hex(4)}"
    first, other = ModuleCache(cache, module, None), ModuleCache(cache, f"{module}x", None)
    await first.set_data("price", Price(price=1200), 60)
    assert await first.get_data("price", Price) == Price(price=1200)
    assert await other.get_data("price", Price) is None
    await first.set_text("broken", "不是 JSON", 60)
    assert await first.get_data("broken", Price) is None
    await first.delete("price")
    assert await first.get_text("price") is None
    with pytest.raises(StepRuleBroken):
        await first.set_text("forever", "x", 0)
    with pytest.raises(StepRuleBroken):
        await first.set_text("huge", "x" * 1_000_001, 60)


class BrokenCache(MemoryCache):
    async def get(self, key: str) -> str | None:
        raise ConnectionError("缓存不可用")

    async def set(self, key: str, value: str, ttl: float) -> None:
        raise ConnectionError("缓存不可用")

    async def delete(self, key: str) -> None:
        raise ConnectionError("缓存不可用")


async def test_cache_failure_is_a_miss() -> None:
    gate = ModuleCache(BrokenCache(), "m", None)
    await gate.set_text("k", "v", 60)
    assert await gate.get_text("k") is None
    await gate.delete("k")


async def test_storage_rules(storage: FileStorage, tmp_path: Path) -> None:
    prefix = f"probe{secrets.token_hex(4)}/"
    source = tmp_path / "source.bin"
    content = secrets.token_bytes(200_000)
    source.write_bytes(content)
    saved = await storage.save_path(f"{prefix}a/1", source)
    assert saved.size == len(content)
    assert b"".join([chunk async for chunk in storage.open(saved.key)]) == content
    assert await storage.exists(saved.key)
    assert not await storage.exists(f"{prefix}a/none")
    assert [item.key async for item in storage.list_objects(prefix)] == [saved.key]
    await storage.delete(saved.key)
    await storage.delete(saved.key)
    assert not await storage.exists(saved.key)
    with pytest.raises(StepRuleBroken):
        await storage.save_path("../outside", source)


async def test_module_files(tmp_path: Path) -> None:
    area = UploadArea(tmp_path / "uploads", 1_000_000, [".txt"])
    files = ModuleFiles(LocalFiles(tmp_path / "files"), area, "notes")

    async def body(data: bytes) -> AsyncIterator[bytes]:
        yield data

    upload = await area.receive("说明.txt", body(b"hello"))
    saved = await files.adopt(upload.temp_id, "north/1")
    assert saved.key == "notes/north/1"
    assert await files.read("north/1", 100) == b"hello"
    with pytest.raises(FileTooLarge):
        await files.read("north/1", 3)
    with pytest.raises(FileTooLarge):
        await area.receive("大.txt", body(b"x" * 1_000_001))
    stale = await area.receive("旧.txt", body(b"old"))
    assert await files.clean_uploads(-1) == 2
    assert not (tmp_path / "uploads" / stale.temp_id).exists()
