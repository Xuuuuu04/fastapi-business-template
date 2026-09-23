"""
模块拿到的 cache 参数 ModuleCache：键自动加上模块名前缀，每个值必须有有效期，大小有上限。
缓存出错时按“没有命中”处理并写日志，不影响业务；命中和未命中次数写进步骤记录。
"""

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
    # 绑定缓存实现、模块名和当前步骤记录。
    def __init__(self, cache: Cache, module: str, record: StepRecord | None) -> None:
        self._cache = cache
        self._prefix = f"{module}:"
        self._record = record

    # 读取文本；没有命中或缓存出错时返回 None。
    async def get_text(self, key: str) -> str | None:
        try:
            value = await self._cache.get(self._prefix + key)
        except Exception:
            log.exception("cache_get_failed key=%s", self._prefix + key)
            value = None
        self._count(value is not None)
        return value

    # 写入文本；ttl 为有效秒数，必须大于零且不超过 7 天。
    async def set_text(self, key: str, value: str, ttl: float) -> None:
        if not 0 < ttl <= MAX_TTL:
            raise StepRuleBroken(f"缓存有效期必须在 0 到 {MAX_TTL} 秒之间")
        if len(value) > MAX_VALUE:
            raise StepRuleBroken(f"缓存值超过 {MAX_VALUE} 个字符，请只缓存必要的数据")
        try:
            await self._cache.set(self._prefix + key, value, ttl)
        except Exception:
            log.exception("cache_set_failed key=%s", self._prefix + key)

    # 读取数据对象；格式与当前类型不符时当作没有命中。
    async def get_data[T: Data](self, key: str, model: type[T]) -> T | None:
        text = await self.get_text(key)
        if text is None:
            return None
        try:
            return model.model_validate_json(text)
        except ValidationError:
            return None

    # 写入数据对象。
    async def set_data(self, key: str, value: Data, ttl: float) -> None:
        await self.set_text(key, value.model_dump_json(), ttl)

    # 删除一个值，用于数据修改后让缓存失效。
    async def delete(self, key: str) -> None:
        try:
            await self._cache.delete(self._prefix + key)
        except Exception:
            log.exception("cache_delete_failed key=%s", self._prefix + key)

    # 记下命中或未命中。
    def _count(self, hit: bool) -> None:
        if self._record is None:
            return
        if hit:
            self._record.cache_hits += 1
        else:
            self._record.cache_misses += 1
