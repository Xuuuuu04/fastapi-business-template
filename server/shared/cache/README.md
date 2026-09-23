# 缓存

`backends.py` 提供进程内和 Redis 实现；`gate.py` 给模块生成带名称前缀的缓存入口。缓存数据必须设置有效期，只能保存可重新计算的内容。进程内缓存不跨进程共享，生产多实例请配置 Redis（`APP_CACHE_URL`）。步骤用 `cache` 参数，存储实现用同名构造参数；命中和未命中次数写进运行记录。缓存服务出错时按未命中处理，不影响业务结果。

```python
class PriceStore:
    def __init__(self, db: Db, cache: ModuleCache) -> None:
        self.db, self.cache = db, cache

    async def price(self, sku: str) -> Price:
        found = await self.cache.get_data(f"price:{sku}", Price)
        if found is None:
            found = await self.read_price(sku)
            await self.cache.set_data(f"price:{sku}", found, 300)
        return found
```
