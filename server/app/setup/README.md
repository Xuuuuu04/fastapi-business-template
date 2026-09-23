# setup：启动组装

| 文件 | 内容 |
| --- | --- |
| [catalog.py](catalog.py) | 模块总目录：启用哪些模块。全项目唯一需要登记模块的地方 |
| [build.py](build.py) | 按配置组装数据库、运行记录、大模型服务、任务表和执行器 |
| [web.py](web.py) | 创建 FastAPI 应用：`uv run uvicorn app.setup.web:create_app --factory` |
| [worker.py](worker.py) | worker 进程：`uv run python -m app.setup.worker` |

接口进程和 worker 进程用同一个 `build()` 组装，保证使用同一份模块目录（启动日志中的 digest 相同）。创建过程不连接数据库；配置不符合生产要求时拒绝启动。
