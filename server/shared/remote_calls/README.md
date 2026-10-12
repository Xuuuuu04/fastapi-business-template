# 外部接口

`remote.py` 定义外部系统的声明和配置，`service.py` 管理连接、超时、重试和概要记录，`gate.py` 限制模块只能访问声明过的外部系统。模块在 `module.py` 登记 `remotes`；步骤在 `@step(remotes=[...])` 里声明，通过 `remote` 参数调用。地址和凭据只写在 `APP_REMOTES` 里。没有请求编号的写入，遇到超时或发送后的连接中断时，需要先检查对方的结果。

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

外部写入收到 5xx、408 或 499 时，不能推定对方已经撤销了这次操作。没有去重编号时只发送一次，报告“结果待确认”；稳定的去重编号只在对方确实支持去重时使用，暂时性故障可以按原编号重试，重试次数用完仍未确认就去查询结果。之后的连接失败或拒绝，不会抹掉较早的未知结果。GET 和 HEAD 的读取保持原来的重试规则。

外部请求记录的 `outcome` 分四种：`not_sent`（还没有发送）、`failed`（对方明确拒绝）、`unknown`（结果未知）和 `ok`（收到成功结果）。同一次最外层操作共享外部写入记录：只要已经有一次写入成功或结果未知，那么之后无论后续步骤、数据库保存还是子流程失败，都报告“结果待确认”，worker 不会自动重发整个操作。数据库回滚只能撤销数据库写入，撤销不了外部效果；单个接口有去重编号，也不能证明整个多步骤流程可以重复。

## 连续失败后暂停调用

外部响应按解压后的实际字节分块读取。`APP_REMOTES` 里每个服务可以设置 `max_response_bytes`，默认 2,000,000 字节，最多 256,000,000 字节，不会只相信对方声明的长度。读取超限时立即关闭响应并且不重试；写入的响应超限说明对方可能已经处理，仍然要先确认结果。大的导出应该分批或使用文件流，不能靠无限加大上限来解决。

[breaker.py](breaker.py) 是熔断器：同一个外部系统（以及大模型服务）连续暂时失败 5 次后，暂停调用 30 秒；暂停期间的请求直接失败，不再每次等到超时。暂停结束后放行一次试探，成功就恢复。对方明确拒绝（参数错误、没有权限、找不到）说明对方服务本身可用，不算进失败。状态保存在各进程的内存里，显示在 `/api/system/runtime` 的 `breakers`。

调用方可以在 `post/put(..., accepted_statuses=(409,))` 之后检查拒绝响应的 JSON 和状态，比如是否明确“未受理”；默认仍然抛出 HTTP 错误。只允许捕获除 408、499 之外的 4xx；不会因为捕获了响应就自动重试，不会把拒绝记录成成功，也不能抹掉更早的未知写入。“受理”的具体含义由业务规则验证，框架不推定任何上游协议。


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

input 和 output 是 Data；响应的包络和确定拒绝的回执也写进 output 的 Data。额外字段默认拒绝，确实需要兼容的额外字段由产品的 Data 显式配置。输入按 JSON 模式和字段别名序列化；GET/HEAD 放查询参数，其他方法放 JSON 正文。path 是声明的站内路径模板，路径参数通过path_fields声明；query_fields与body_fields分别分配查询和正文，未显式分配时沿用GET/HEAD查询、其他方法JSON正文。FilePart通过file_fields声明并检查总大小，文件名不包含本地路径；大批量原件使用产物引用。receipt_fields要求本次回执实际提供关键字段，运行记录保留模板路径，不记录路径参数原文。协议shape显示实际字段与扩展策略，空模型或任意扩展只标部分验证。

安全性以 effect 为准，不从 HTTP 方法猜测：POST 做读取可以重试，GET 做写入仍然要有待确认保护。unknown_on 是上游协议额外的 HTTP 待确认状态（例如 202），它不会弱化原有的 408/499/5xx、超时、响应超限和较早未知写入的保护。accepted_statuses 沿用 2.2 的定义，只支持确定的 4xx，和 unknown_on 不能重叠；“受理/未受理”的具体含义由产品核对回执确认。成功写入的回执校验失败，也报待确认；确定拒绝的回执校验失败，报协议字段错误。记录里只有有限的字段路径和错误类别，不记录正文或取值；运行图显示接口名、状态和耗时。

启动检查会发现同名但不同对象、漏登记、以及源码里能识别出来的漏声明调用；动态路径只能在运行时校验，不声称静态检查能证明所有 Python 路径。声明摘要涵盖协议字段和步骤引用。旧的 get/post/put/delete/send 在启动时提醒迁移，行为不变；迁移完成后设置 `APP_REMOTE_ENDPOINTS_STRICT=true`，能识别的旧调用在启动时报错，剩余的旧调用在运行时报错。独立的读、写和未知样例在 tests/framework/endpoint_sample.py；模板不登记业务模块。

外部写入的持久意图与恢复使用[ProviderSpec和统一效果入口](../effects/README.md)。HttpAdapter复用当前连接池和协议，但只发送一次；SMTP和SDK使用相同的未知保护。新产品不要把旧接口的请求编号自动重试规则当成供应商重复保证。
