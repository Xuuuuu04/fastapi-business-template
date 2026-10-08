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
| 任务完成状态与业务结果同一事务提交，并检查尝试编号 | 过期的尝试不能覆盖新结果，它的业务写入会被撤销 |
| 只有 `repeat_safe=True` 的任务在期限过期后自动重新排队 | 其他任务可能已经产生外部效果，标为“结果待确认”由人判断 |
| 只有暂时故障和超时按 `Retry` 重试 | 输入错误、程序缺陷重试也不会成功 |
| 每类任务有排队上限，用计数行原子加一 | 多个接口实例同时登记也不会超过上限；满了明确拒绝 |
| 登记时记下模块版本，版本变了就等待人工确认 | 不让旧任务悄悄按新规则执行 |
| 同一个请求编号（Idempotency-Key）只受理一次 | 重复提交返回原任务；内容不同时报冲突 |

定时任务登记失败时，不把当前时段当作已经完成；队列容量恢复后会继续尝试。

worker 停止领取任务后，先按退出等待时间等待在途任务；超时后取消任务，等回滚、连接归还和续期任务清理完成，再关闭共用服务。清理时的普通异常会明确报错。

设置 `APP_JOB_HEALTH_FILE` 后，正常领取与维护循环每五秒最多更新一次健康文件；失败不刷新，停止时删除。文件放在 worker 自己的临时目录，不能使用共享业务卷的固定文件。`python -m app.setup.worker_health` 检查时间是否有效，默认有效期 60 秒；有效期至少比轮询间隔长 30 秒。健康只说明循环近期可用，任务成功仍以任务结果为准。

服务密钥任务在执行前按当前配置重新读取权限；用户任务沿用登记时的身份与权限。业务要求停用用户或撤销角色后立即阻止排队任务时，执行步骤必须重新读取用户状态，不能只依赖任务中的旧身份。

使用 SQLite 时只能运行一个 worker；多个 worker 需要 PostgreSQL。人工处理用 `uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs`。

## 显式分段提交（2.1）

普通操作仍在最外层一次提交。大规模批处理可声明：

```python
JobPlan(process_batch, segmented=True, repeat_safe=True, lease_seconds=60)
```

每次操作只处理一批。步骤可以注入 `checkpoint: Checkpoint`（从 `shared.public` 导入）：

```python
start = checkpoint.cursor.get("after", 0)  # 已提交的位置，首次为空字典
# 用读取步骤确定本批范围，再用 saves=True 的步骤保存本批结果。
checkpoint.advance({"after": next_id}, rows=batch_count)
# 最后一批用 checkpoint.finish(rows=batch_count, cursor={"after": next_id})。
```

`advance/finish` 只声明提交点；整个本批操作成功结束后框架才提交。每次调用只能声明一次；
继续执行必须推进游标，游标是最多16 KiB的 JSON 字典，不放业务正文或凭据。
框架将业务写入、游标、段证据及最后一批任务完成状态放在同一事务，随后释放连接，重新调用操作。
失败只撤销尚未提交的批次，之前各批保留；租约过期的旧尝试不能提交或通过续租复活。
每批开始前续租并检查停止信号。正常停止等当前批完成再退出；若本批超时或进程被强杀，
本批事务回滚，恢复时从上一个提交点继续。分段任务不会被短的退出等待时间中途取消。
单批耗时应控制在部署退出等待以内：模板 Compose 的 worker `stop_grace_period` 默认30秒，
超过后容器仍会被强杀。框架的 `APP_JOB_SHUTDOWN_SECONDS`（`job_shutdown_seconds`）默认20秒；
按两者较小值并留出提交余量选择批大小。批次总耗时超过 `job_shutdown_seconds` 时，运行记录给出
提醒，不改变业务结果或自动重做。确需长批次时，同步调整部署停止宽限，不能只改框架配置。
零售长汇算升级时，应实测读取、计算和提交的总耗时，按这个标准选择批大小。
输入范围必须固定，游标格式变化要升级模块版本；单批也要控制在合理的内存和租约期限内。
这不会自动分页或并行处理 SQL，需要业务明确每批的读取范围。

外部写入不能由数据库回滚。分段任务发送前先独立保存写入意图；
写入之后本批失败、取消或失联，任务保留“结果待确认”，不自动重发。
即使在意图保存后、实际发送前退出，也保守等待人工核对。
先查询原请求结果，再明确执行 `jobs requeue 任务编号 --yes` 才清除意图并从原游标恢复；
重新排队不等于确认平台没执行。对无法安全恢复的外部写入，继续用单次提交和查询两个操作。

任务详情、运行图和段证据显示批号、恢复游标、本批行数和耗时、累计已提交行数：

```bash
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs segments 任务编号
```

也可查询 `GET /api/jobs/{任务编号}/segments?after=0&limit=50`，权限与任务详情一致，
`next_after` 用于下一页。段证据持久保存；完整步骤和 SQL 记录跨进程保留需配置
`APP_RUN_RECORDS=database`。普通短操作不需要 checkpoint，也不访问新增状态表。

已有产品用模板更新脚本预览框架变化，保留产品自己的迁移链。
在当前数据库版本后增加两张框架表的增量迁移（参考模板 `a8c42f910d37`），
先在隔离库迁移和检查，再部署；不要拷贝模板初始迁移覆盖产品历史。
独立十万行强杀恢复样例见 `tests/framework/segment_sample.py` 与 `test_segmented_jobs.py`。
