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

调用方可在`post/put(..., accepted_statuses=(409,))`后检查拒绝响应的JSON与状态，
如是否明确“未受理”；默认仍抛出HTTP错误。只允许捕获除408、499外的4xx，
不因捕获响应自动重试，不把拒绝记录为成功，也不能抹掉更早的未知写入。
接口受理含义由业务规则验证，框架不推定任何具体上游协议。


## 声明上游协议

协议只定义一次，放在业务 `module.py` 或 `store/contract.py`，需要跨包复用时从
该包 `public.py` 导出同一对象。消费包在 `Module.endpoints` 登记引用，步骤声明
`endpoints=[query]`；经store调用也在步骤声明，存储不会扩大步骤权限。

```python
query = Endpoint(
    "supplier.query_price",
    "POST",
    "/prices/query",
    input=Query,
    output=Receipt,
    effect="read",
)
change = Endpoint(
    "supplier.change_price",
    "POST",
    "/prices/change",
    input=Change,
    output=Receipt,
    effect="write",
    unknown_on=(202,),
    accepted_statuses=(409,),
)
module = Module(..., remotes=(supplier,), endpoints=(query, change))


@step("查询价格", reads=["sku"], writes=["receipt"], remotes=[supplier], endpoints=[query])
async def read_price(data: Work, remote: RemoteClient) -> None:
    reply = await remote.call(supplier, query, Query(sku=data.sku))
    data.receipt = reply.data  # 已校验的Receipt；reply.status保留HTTP状态
```

input/output是Data；响应包络与确定拒绝回执也写进output Data，额外字段默认拒绝，
确需兼容的额外字段由产品Data显式配置。输入按JSON模式及字段别名序列化；GET/HEAD
放查询参数，其他方法放JSON正文。path是固定站内绝对路径，动态参数在input中传递。
本版不提供文件上传、任意正文及动态路径模板；这些旧调用保留并提示迁移。

安全性以effect为准，不从HTTP方法猜测：POST读取可重试，GET写入仍需待确认保护。
unknown_on是上游协议额外的HTTP待确认状态（例如202），不会弱化原408/499/5xx、
超时、响应超限和较早未知写入的保护。accepted_statuses沿用2.2，仅支持确定4xx，
与unknown_on不能重叠；具体“受理/未受理”含义由产品核对回执。
成功写入回执校验失败也报待确认；确定拒绝回执校验失败报协议字段错误。
只记录有限字段路径/错误类别，不记录正文或取值，运行图显示接口名、状态和耗时。

启动检查发现同名不同对象、漏登记和源码中可识别的漏声明调用；动态路径只能在
运行时校验，不声称静态检查能证明所有Python路径。声明摘要涵盖协议字段与步骤引用。
旧get/post/put/delete/send启动时提醒迁移，行为不变；完成迁移后设置
`APP_REMOTE_ENDPOINTS_STRICT=true`，可识别旧调用在启动报错，剩余旧调用在运行时报错。
独立读/写及未知样例在tests/framework/endpoint_sample.py；模板不登记业务模块。
