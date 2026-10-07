# errors：错误种类

- [kinds.py](kinds.py)：错误种类 `Kind` 和业务错误的写法 `BusinessError`。种类决定 HTTP 状态码和任务能否重试。
- [framework.py](framework.py)：框架自己抛出的错误，例如未登录、无权限、排队已满、超时、结果待确认、步骤违反声明。
- [details.py](details.py)：异常日志的安全文字，只保留意外异常类型与调用位置，已定义的业务错误保留公开原因。

业务错误写在模块的 data.py：

```python
class ProductMissing(BusinessError):
    code = "product_missing"  # 稳定的错误码，调用方按它判断
    kind = Kind.NOT_FOUND  # 决定状态码 404
    message = "商品不存在"  # 默认中文说明，可以改
```

程序按错误码和种类判断，不要按说明文字判断：说明文字可以随时改进，判断逻辑不应因此改变。
