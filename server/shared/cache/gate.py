import logging

from pydantic import ValidationError

from shared.cache.backends import Cache
from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.records.models import StepRecord

log = logging.getLogger("server.cache")

MAX_TTL = 7 * 86400
MAX_VALUE = 1_000_000


class ModuleCache:
    def __init__(self, cache: Cache, module: str, record: StepRecord | None) -> None:
        self._cache = cache
        self._prefix = f"{module}:"
        self._record = record

    async def get_text(self, key: str) -> str | None:
        try:
            value = await self._cache.get(self._prefix + key)
        except Exception:
            log.exception("cache_get_failed key=%s", self._prefix + key)
            value = None
        self._count(value is not None)
        return value

    async def set_text(self, key: str, value: str, ttl: float) -> None:
        if not 0 < ttl <= MAX_TTL:
            raise StepRuleBroken(f"缓存有效期必须在 0 到 {MAX_TTL} 秒之间")
        if len(value) > MAX_VALUE:
            raise StepRuleBroken(f"缓存值超过 {MAX_VALUE} 个字符，请只缓存必要的数据")
        try:
            await self._cache.set(self._prefix + key, value, ttl)
        except Exception:
            log.exception("cache_set_failed key=%s", self._prefix + key)

    async def get_data[T: Data](self, key: str, model: type[T]) -> T | None:
        text = await self.get_text(key)
        if text is None:
            return None
        try:
            return model.model_validate_json(text)
        except ValidationError:
            return None

    async def set_data(self, key: str, value: Data, ttl: float) -> None:
        await self.set_text(key, value.model_dump_json(), ttl)

    async def delete(self, key: str) -> None:
        try:
            await self._cache.delete(self._prefix + key)
        except Exception:
            log.exception("cache_delete_failed key=%s", self._prefix + key)

    def _count(self, hit: bool) -> None:
        if self._record is None:
            return
        if hit:
            self._record.cache_hits += 1
        else:
            self._record.cache_misses += 1
