# jobs：后台任务与定时计划

任务存在业务数据库的任务表中，任务表本身就是队列，不需要 RabbitMQ 或 Celery。

## 文件

| 文件 | 内容 |
| --- | --- |
| [plan.py](plan.py) | `JobPlan`、`Retry`、`Schedule`：写在模块的 module.py 中 |
| [tables.py](tables.py) | 任务表和排队计数表 |
| [queue.py](queue.py) | 登记、领取（`FOR UPDATE SKIP LOCKED`）、完成、失败、延长期限、期限过期处理 |
| [worker.py](worker.py) | worker 主循环 |
| [schedule.py](schedule.py) | 定时计划 |
| [views.py](views.py) | 查询任务，人工重新排队和取消 |

## 规则与原因

| 规则 | 原因 |
| --- | --- |
| 任务与业务写入在同一事务中登记 | 不会出现“业务保存了但任务没登记”或反过来 |
| 任务完成状态与业务结果同一事务提交，并核对尝试编号 | 过期的尝试不能覆盖新结果，它的业务写入会被撤销 |
| 只有 `repeat_safe=True` 的任务在期限过期后自动重新排队 | 其他任务可能已经产生外部效果，标为“结果待核对”由人判断 |
| 只有暂时故障和超时按 `Retry` 重试 | 输入错误、程序缺陷重试也不会成功 |
| 每类任务有排队上限，用计数行原子加一 | 多个接口实例同时登记也不会超过上限；满了明确拒绝 |
| 登记时记下模块版本，版本变了就等待人工确认 | 不让旧任务悄悄按新规则执行 |
| 同一个请求编号（Idempotency-Key）只受理一次 | 重复提交返回原任务；内容不同时报冲突 |

定时任务登记失败时，不把当前时段当作已经完成；队列容量恢复后会继续尝试。

使用 SQLite 时只能运行一个 worker；多个 worker 需要 PostgreSQL。人工处理用 `uv run python -m tools.jobs`。
