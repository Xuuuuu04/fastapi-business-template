# events：模块事件

模块之间除了用 `call` 同步调用，还可以用事件解耦：发布方只说“发生了什么”，不知道谁会处理。

```python
# 发布方 order_quote/public.py
quote_created = event("order_quote.quote_created", "报价已创建", data=QuoteCreated)


# 发布方的步骤：参数 publish，声明 publishes 和 saves=True
@step("通知报价已创建", reads=["quote"], publishes=[quote_created], saves=True)
async def announce_quote(data: QuoteWork, publish: Publish) -> None:
    await publish(quote_created, QuoteCreated(quote_id=data.quote.id))


# 订阅方 module.py：事件发生后由本模块的操作处理，输入类型就是事件数据
Module(..., subscribes=(on(quotes.quote_created, public.record_quote),))
```

| 规则 | 原因 |
| --- | --- |
| 事件与发布它的业务写入在同一事务中登记到任务表 | 业务回滚时事件也不会发出；业务提交后事件一定会被处理 |
| 订阅方由 worker 异步执行，默认失败重试 3 次 | 订阅方出错不影响发布方，也不拖慢发布方的响应 |
| 订阅方以“事件”身份执行，只有处理操作所需的权限，组织范围沿用发布时的调用者 | 最小权限，组织隔离不被绕过 |
| 发布方模块被关闭时，订阅它的模块启动检查失败 | 不会出现永远等不到的订阅 |
| 同一次运行中的同一次发布只登记一次 | 发布步骤重试时不重复处理 |

| 文件 | 内容 |
| --- | --- |
| [event.py](event.py) | `event()`、`on()` 声明 |
| [publish.py](publish.py) | 步骤中的 `publish` 工具 |
| [checks.py](checks.py) | 启动检查 |
