# setup：启动组装

| 文件 | 内容 |
| --- | --- |
| [catalog.py](catalog.py) | 模块总目录：登记项目包含的模块；配置 APP_DISABLED_MODULES 关闭不使用的模块及其接口 |
| [build.py](build.py) | 按配置组装数据库、运行记录、大模型服务、任务表和执行器 |
| [web.py](web.py) | 创建 FastAPI 应用：`uv run uvicorn app.setup.web:create_app --factory` |
| [worker.py](worker.py) | worker 进程：`uv run python -m app.setup.worker` |

接口进程和 worker 进程用同一个 `build()` 组装，保证使用同一份模块目录（启动日志中的 digest 相同）。创建过程不连接数据库；配置不符合生产要求时拒绝启动。

公共服务按已有声明准备：模块声明提示词才创建大模型服务；存储参数中使用 `files`、`legacy`、`vault` 才准备对应资源。外部系统只保留启用模块声明的地址。缓存仍供请求频率限制使用，登录令牌检查仍要求生产密钥。
