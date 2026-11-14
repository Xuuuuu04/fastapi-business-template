import asyncio
from collections import OrderedDict
from collections.abc import Awaitable
from typing import Protocol

import redis.asyncio as redis_client
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from shared.errors.framework import CacheUnavailable
from shared.timing.current import monotonic


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl: float) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def incr(self, key: str, ttl: float) -> int: ...

    async def close(self) -> None: ...


class MemoryCache:
    def __init__(self, max_entries: int = 10000) -> None:
        self.max_entries = max_entries
        self.rows: OrderedDict[str, tuple[str, float]] = OrderedDict()

    async def get(self, key: str) -> str | None:
        found = self.rows.get(key)
        if found is None:
            return None
        if found[1] <= monotonic():
            del self.rows[key]
            return None
        self.rows.move_to_end(key)
        return found[0]

    async def set(self, key: str, value: str, ttl: float) -> None:
        self.rows[key] = (value, monotonic() + ttl)
        self.rows.move_to_end(key)
        while len(self.rows) > self.max_entries:
            self.rows.popitem(last=False)

    async def delete(self, key: str) -> None:
        self.rows.pop(key, None)

    async def incr(self, key: str, ttl: float) -> int:
        current = await self.get(key)
        if current is None:
            await self.set(key, "1", ttl)
            return 1
        count = int(current) + 1
        expires = self.rows[key][1]
        self.rows[key] = (str(count), expires)
        return count

    async def close(self) -> None:
        return None


class RedisCache:
    def __init__(self, url: str, *, timeout: float = 3, max_connections: int = 50) -> None:
        self.timeout = timeout
        self.client = redis_client.from_url(
            url,
            decode_responses=True,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            max_connections=max_connections,
            retry=Retry(NoBackoff(), 0),
        )

    async def perform[T](self, operation: Awaitable[T]) -> T:
        try:
            async with asyncio.timeout(self.timeout):
                return await operation
        except (TimeoutError, RedisError) as error:
            raise CacheUnavailable() from error

    async def get(self, key: str) -> str | None:
        value = await self.perform(self.client.get(key))
        return None if value is None else str(value)

    async def set(self, key: str, value: str, ttl: float) -> None:
        await self.perform(self.client.set(key, value, px=max(1, int(ttl * 1000))))

    async def delete(self, key: str) -> None:
        await self.perform(self.client.delete(key))

    async def incr(self, key: str, ttl: float) -> int:
        script = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 or redis.call('PTTL', KEYS[1]) < 0 then
            redis.call('PEXPIRE', KEYS[1], ARGV[1])
        end
        return count
        """
        return int(
            await self.perform(
                self.client.execute_command("EVAL", script, 1, key, max(1, int(ttl * 1000)))
            )
        )

    async def close(self) -> None:
        await self.client.aclose()
