"""
缓存和文件存储的约定测试：进程内缓存与 Redis、本地目录与 S3 兼容存储对同一组操作给出相同结果。
进程内缓存和本地目录每次都测；Redis 和 S3 只在设置下列环境变量时参加，否则跳过：
  APP_TEST_REDIS_URL        例如 redis://127.0.0.1:6379/15
  APP_TEST_S3_ENDPOINT      例如 http://127.0.0.1:9000（MinIO）
  APP_TEST_S3_BUCKET、APP_TEST_S3_ACCESS_KEY、APP_TEST_S3_SECRET_KEY、APP_TEST_S3_REGION
"""

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


# 缓存格式测试使用的价格数据，单位为分。
class Price(Data):
    price: int = meaning("价格", unit="分")


# 按名称创建缓存实现；Redis 没有配置时跳过。
@pytest.fixture(params=["memory", "redis"])
async def cache(request: pytest.FixtureRequest) -> AsyncIterator[Cache]:
    url = os.environ.get("APP_TEST_REDIS_URL", "")
    if request.param == "redis" and not url:
        pytest.skip("没有设置 APP_TEST_REDIS_URL")
    backend: Cache = MemoryCache() if request.param == "memory" else RedisCache(url)
    yield backend
    await backend.close()


# 按名称创建文件存储；S3 没有配置时跳过。
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


# 读写、删除、过期和计数在各实现中一致；计数过期后从 1 重新开始。
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


# 模块缓存加模块前缀，数据对象可以往返；格式不符当作未命中，并计入命中统计。
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


# 故意连接失败的测试缓存，用来检查故障返回与健康状态。
class BrokenCache(MemoryCache):
    # 每个操作都报连接错误，模拟缓存服务不可用。
    async def get(self, key: str) -> str | None:
        raise ConnectionError("缓存不可用")

    # 写入时报连接错误。
    async def set(self, key: str, value: str, ttl: float) -> None:
        raise ConnectionError("缓存不可用")

    # 删除时报连接错误。
    async def delete(self, key: str) -> None:
        raise ConnectionError("缓存不可用")


# 缓存服务出错时按未命中处理，业务照常执行，不抛出异常。
async def test_cache_failure_is_a_miss() -> None:
    gate = ModuleCache(BrokenCache(), "m", None)
    await gate.set_text("k", "v", 60)
    assert await gate.get_text("k") is None
    await gate.delete("k")


# 保存、分块读取、列出、删除在各实现中一致；删除两次不报错，越界的键被拒绝。
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


# 模块文件入口：临时上传保存为带模块前缀的正式文件；读取超过上限时报错；过期临时文件被清理。
async def test_module_files(tmp_path: Path) -> None:
    area = UploadArea(tmp_path / "uploads", 1_000_000, [".txt"])
    files = ModuleFiles(LocalFiles(tmp_path / "files"), area, "notes")

    # 把一段内容当作上传正文。
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
