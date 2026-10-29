# api：HTTP 接口

| 位置 | 内容 |
| --- | --- |
| [middleware.py](middleware.py) | 请求编号、正文大小和并发限制、请求日志、安全响应头；响应头带 X-Request-ID、X-Run-ID |
| [errors.py](errors.py) | 把异常统一转成错误响应，内部细节不外露 |
| [replies.py](replies.py) | 统一错误格式、任务受理格式、按操作生成接口文档的错误说明 |
| [identity.py](identity.py) | 识别调用者：服务密钥、Bearer 令牌、本地开发身份、匿名；按调用者限流 |
| [runner.py](runner.py) | 路由使用的执行入口 `RunDep`：只能执行登记过的操作或登记任务；`run(..., limits=(FailureLimit(...),))` 声明哪些业务错误要计数、几次后返回 429 |
| [routers.py](routers.py) | 全部路由的清单 |
| [v1](v1/) | 业务接口第 1 版 |
| [system](system/) | 健康检查、运行排查、运行统计、操作记录查询、排查网页、任务查询 |

## 返回格式

正常结果直接返回数据本身；错误使用正确的 HTTP 状态码和统一结构：

```json
{"code": "file_missing", "kind": "not_found", "message": "商品 9 不存在",
 "request_id": "8acf9b04eb0d9300", "run_id": "f51c4dacdbdcca79", "fields": []}
```

程序按 `code` 判断；拿 `run_id` 查询 `/api/system/runs/{run_id}/report` 就能看到这次执行停在哪一步、为什么。

`fields` 最多返回 50 项，完整路径最多 200 个 UTF-8 字节，问题说明最多 300 个 UTF-8 字节。过长或非法路径不返回为控件错误，继续看整体说明；不要把截断后的路径当作另一个字段。大量输入问题先修正已显示的部分，再提交检查，避免错误正文超过调用方的读取上限。
