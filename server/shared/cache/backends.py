"""
缓存的统一约定 Cache 和两个实现：进程内缓存 MemoryCache、Redis 缓存 RedisCache。
缓存只放可以过期、可以重新计算的数据，不能当作业务数据的来源；每个值都必须有有效期。
多实例部署时用 Redis，进程内缓存在各进程之间不共享。
"""

import time
from collections import OrderedDict
from typing import Protocol

import redis.asyncio as redis_client


class Cache(Protocol):
    # 读取一个值，不存在或已过期时返回 None。
    async def get(self, key: str) -> str | None: ...

    # 写入一个值，ttl 为有效秒数。
    async def set(self, key: str, value: str, ttl: float) -> None: ...

    # 删除一个值。
    async def delete(self, key: str) -> None: ...

    # 计数加一并返回新值；第一次计数时设置有效期，用于限流。
    async def incr(self, key: str, ttl: float) -> int: ...

    # 释放连接。
    async def close(self) -> None: ...


class MemoryCache:
    # 设置最多保存多少个值，超出时丢弃最久没有使用的。
    def __init__(self, max_entries: int = 10000) -> None:
        self.max_entries = max_entries
        self.rows: OrderedDict[str, tuple[str, float]] = OrderedDict()

    # 读取一个值。
    async def get(self, key: str) -> str | None:
        found = self.rows.get(key)
        if found is None:
            return None
        if found[1] <= time.monotonic():
            del self.rows[key]
            return None
        self.rows.move_to_end(key)
        return found[0]

    # 写入一个值，超出容量时丢弃最久没有使用的。
    async def set(self, key: str, value: str, ttl: float) -> None:
        self.rows[key] = (value, time.monotonic() + ttl)
        self.rows.move_to_end(key)
        while len(self.rows) > self.max_entries:
            self.rows.popitem(last=False)

    # 删除一个值。
    async def delete(self, key: str) -> None:
        self.rows.pop(key, None)

    # 计数加一；过期后重新从 1 开始。
    async def incr(self, key: str, ttl: float) -> int:
        current = await self.get(key)
        if current is None:
            await self.set(key, "1", ttl)
            return 1
        count = int(current) + 1
        expires = self.rows[key][1]
        self.rows[key] = (str(count), expires)
        return count

    # 进程内缓存没有需要释放的资源。
    async def close(self) -> None:
        return None


class RedisCache:
    # 使用 Redis 地址创建连接池。
    def __init__(self, url: str) -> None:
        self.client = redis_client.from_url(url, decode_responses=True)

    # 读取一个值。
    async def get(self, key: str) -> str | None:
        value = await self.client.get(key)
        return None if value is None else str(value)

    # 写入一个值，有效期精确到毫秒。
    async def set(self, key: str, value: str, ttl: float) -> None:
        await self.client.set(key, value, px=max(1, int(ttl * 1000)))

    # 删除一个值。
    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    # 计数加一；第一次计数时设置有效期。
    async def incr(self, key: str, ttl: float) -> int:
        count = int(await self.client.incr(key))
        if count == 1:
            await self.client.pexpire(key, max(1, int(ttl * 1000)))
        return count

    # 关闭连接池。
    async def close(self) -> None:
        await self.client.aclose()
