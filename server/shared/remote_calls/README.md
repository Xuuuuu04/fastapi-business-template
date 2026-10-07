# 外部接口

`remote.py` 定义外部系统声明和配置，`service.py` 管理连接、超时、重试与概要记录，`gate.py` 限制模块访问已声明的外部系统。模块在 `module.py` 登记 `remotes`，步骤在 `@step(remotes=[...])` 声明并通过 `remote` 参数调用。地址与凭据只写入 `APP_REMOTES`；没有请求编号的写入遇到超时或发送后的连接中断时，需要检查对方结果。

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

外部写入收到 5xx、408 或 499 时，不能推定对方已经撤销。没有去重编号时仅发一次并报告结果待确认；稳定编号只在对方确实支持去重时使用，暂时故障可按原编号重试，次数用完仍未确认就查询结果。之后的连接失败或拒绝不会抹掉较早的未知结果。GET 与 HEAD 的读取保持原重试规则。

外部请求记录的 `outcome` 区分 `not_sent`（尚未发送）、`failed`（明确拒绝）、`unknown`（结果未知）和 `ok`（收到成功结果）。同一次最外层操作共享外部写入记录：只要已有写入成功或结果未知，后续步骤、数据库保存或子流程之后失败，都报告结果待确认，worker 不自动重发整个操作。数据库回滚只能撤销数据库写入，不能撤销外部效果。单个接口的去重编号也不能证明整个多步骤流程可以重复。

## 连续失败后暂停调用

外部响应按解压后的实际字节分块读取，`APP_REMOTES` 每个服务可设置 `max_response_bytes`，默认 2,000,000 字节，最多 256,000,000 字节。不会只相信声明的长度。读取超限立即关闭响应且不重试；写入响应超限说明对方可能已经处理，仍须先确认结果。大导出应分批或使用文件流，不能通过无限增加上限处理。

[breaker.py](breaker.py)：同一个外部系统（以及大模型服务）连续暂时失败 5 次后暂停调用 30 秒，暂停期间直接失败，不再每次等到超时；暂停结束放行一次试探，成功就恢复。对方明确拒绝（参数错误、没有权限、找不到）说明对方可用，不算失败。状态保存在各进程内存中，显示在 `/api/system/runtime` 的 `breakers`。
