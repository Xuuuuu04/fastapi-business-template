# 外部接口

`remote.py` 定义外部系统声明和配置，`service.py` 管理连接、超时、重试与概要记录，`gate.py` 限制模块访问已声明的外部系统。模块在 `module.py` 登记 `remotes`，步骤在 `@step(remotes=[...])` 声明并通过 `remote` 参数调用。地址与凭据只写入 `APP_REMOTES`；没有请求编号的写入遇到超时或发送后的连接中断时，需要核对对方结果。

```python
# module.py
supplier = remote("supplier", "供应商价格接口")
module = Module(..., remotes=(supplier,))


# steps/
@step("查询供应商价格", reads=["sku"], writes=["cost"], remotes=[supplier])
async def ask_supplier(data: QuoteWork, remote: RemoteClient) -> None:
    reply = await remote.get(supplier, f"/prices/{data.sku}")
    data.cost = int(reply.data["price"])
```

配置示例：`APP_REMOTES={"supplier": {"base_url": "https://supplier.example", "token": "..."}}`。生产环境中声明了但没有配置的外部系统会让服务拒绝启动。
