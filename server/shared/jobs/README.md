# jobs：后台任务与定时计划

任务保存在业务数据库的任务表里，任务表本身就是队列，不需要 RabbitMQ 或 Celery。

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
| 任务与业务写入在同一事务中登记 | 不会出现"业务保存了但任务没登记"或反过来 |
| 任务完成状态与业务结果同一事务提交，并检查尝试编号 | 过期的尝试不能覆盖新结果，它的业务写入会被撤销 |
| 只有 `repeat_safe=True` 的任务在期限过期后自动重新排队 | 其他任务可能已经产生外部效果，标为"结果待确认"由人判断 |
| 只有暂时故障和超时按 `Retry` 重试 | 输入错误、程序缺陷重试也不会成功 |
| 每类任务有排队上限，用计数行原子加一 | 多个接口实例同时登记也不会超过上限；满了明确拒绝 |
| 登记时记下模块版本，版本变了就等待人工确认 | 不让旧任务悄悄按新规则执行 |
| 同一个请求编号（Idempotency-Key）只受理一次 | 重复提交返回原任务；内容不同时报冲突 |

定时任务登记失败时，不会把当前时段当作已经完成；队列容量恢复后会继续尝试。

worker 停止领取任务后，先按退出等待时间等待在途任务；超时后取消任务，等回滚、连接归还和续期任务清理都完成，再关闭共用服务。清理时出现的普通异常会明确报错。

设置 `APP_JOB_HEALTH_FILE` 之后，正常的领取和维护循环每五秒最多更新一次健康文件；失败时不刷新，停止时删除。文件要放在 worker 自己的临时目录，不能用共享业务卷上的固定文件。用 `python -m app.setup.worker_health` 检查时间是否有效，默认有效期 60 秒；有效期至少要比轮询间隔长 30 秒。健康只能说明循环近期可用，任务是否成功仍以任务结果为准。

服务密钥的任务在执行前按当前配置重新读取权限；用户任务沿用登记时的身份和权限。如果业务要求"停用用户或撤销角色后立即阻止已排队的任务"，执行步骤必须重新读取用户状态，不能只依赖任务里保存的旧身份。

使用 SQLite 时只能运行一个 worker；多个 worker 需要 PostgreSQL。人工处理任务用 `uv run dev jobs`。

## 怎么选普通、分段、多阶段

普通短任务：`JobPlan(create_record, repeat_safe=True)`，和普通 HTTP 操作用同一个 Flow；一次提交，失败全部回滚。repeat_safe 必须来自实际的幂等规则，不因为任务很短就填 true。

固定范围的批量导入：`JobPlan(import_rows, segmented=True, repeat_safe=True, cursor=Cursor)`；每次只读写一批，保存步骤推进 checkpoint，之前提交的批次不会回滚。这不是自动分页，游标和范围仍然要由业务声明。

采集、等待、汇算、发布：在 module.py 登记 `Pipeline/Stage/Wait`，各阶段登记公开操作和 JobPlan，首入口的 Schedule 引用 pipeline.start。例：

```python
Schedule(
    "daily",
    "日报定时入口",
    daily.start,
    daily.start.input(request=StartRequest[Begin](data=Begin())),
    every=timedelta(days=1),
    slot_input_field="request.period",
)
```

daily 是[flow 说明](../flow/README.md)里已声明的 Pipeline。Wait 操作输出 ready 布尔值；每次只检查一次，等待由框架推进。某个汇算 Stage 很大时可以用分段的 JobPlan，段游标的 Data 会进入声明兼容检查。不要在普通任务里等待外部数据，也不要在一个事务里串起全部阶段；外部结果未知时先人工核实，不盲目重排。

完整独立样例和原件演练见 tests/framework/drill_sample.py、[演练说明](../drills/README.md)。声明和测试样例通过不代表真实业务完成；要按真实规模演练整条链并核对结果，再补局部细节。

## 显式分段提交（2.1）

普通操作仍然在最外层一次提交。大规模批处理可以声明：

```python
JobPlan(process_batch, segmented=True, repeat_safe=True, lease_seconds=60)
```

每次操作只处理一批。步骤可以注入 `checkpoint: Checkpoint`（从 `shared.public` 导入）：

```python
start = checkpoint.cursor.get("after", 0)
checkpoint.advance({"after": next_id}, rows=batch_count)
```

`checkpoint.cursor` 是已提交的位置，第一批为空字典。本批范围用读取步骤确定，结果用 `saves=True` 的步骤保存；最后一批改用 `checkpoint.finish(rows=batch_count, cursor={"after": next_id})`。

`advance/finish` 只声明提交点；整个本批操作成功结束后框架才提交。每次调用只能声明一次；继续执行必须推进游标。游标是最多 16 KiB 的 JSON 字典，不放业务正文或凭据。框架把业务写入、游标、段证据和最后一批的任务完成状态放在同一事务里，随后释放连接、重新调用操作。

失败只撤销尚未提交的批次，之前各批保留；租约过期的旧尝试不能提交，也不能靠续租复活。每批开始前续租并检查停止信号。正常停止会等当前批完成再退出；如果本批超时或进程被强杀，本批事务回滚，恢复时从上一个提交点继续。分段任务不会被短的退出等待时间中途取消。

单批耗时应该控制在部署的退出等待以内：模板 Compose 里 worker 的 `stop_grace_period` 默认 30 秒，超过后容器仍会被强杀；框架的 `APP_JOB_SHUTDOWN_SECONDS`（`job_shutdown_seconds`）默认 20 秒。按两者中较小的值、并留出提交余量来选择批大小。批次总耗时超过 `job_shutdown_seconds` 时，运行记录会给出提醒，但不改变业务结果、也不会自动重做。确实需要长批次时，要同步调整部署的停止宽限，不能只改框架配置。产品升级长汇算时，应实测读取、计算和提交的总耗时，按这个标准选择批大小。输入范围必须固定；游标格式变化要升级模块版本；单批也要控制在合理的内存和租约期限内。框架不会自动分页或并行处理 SQL，每批的读取范围要由业务明确。

外部写入不能靠数据库回滚。分段任务发送前先独立保存写入意图；写入之后本批失败、取消或失联，任务保留"结果待确认"，不自动重发。即使在保存意图之后、实际发送之前退出，也保守地等待人工核对。先查询原请求的结果，再显式执行 `jobs requeue 任务编号 --yes` 才清除意图并从原游标恢复；重新排队不等于确认平台没有执行。对无法安全恢复的外部写入，继续用"单次提交 + 查询"两个操作。

任务详情、运行图和段证据会显示批号、恢复游标、本批行数和耗时、累计已提交行数：

```bash
uv run dev jobs segments 任务编号
```

也可以查询 `GET /api/jobs/{任务编号}/segments?after=0&limit=50`，权限与任务详情一致，`next_after` 用于下一页。段证据持久保存；完整步骤和 SQL 记录跨进程保留需要配置 `APP_RUN_RECORDS=database`。普通短操作不需要 checkpoint，也不访问新增的状态表。

已有产品用模板更新脚本预览框架变化，保留产品自己的迁移链。在当前数据库版本之后增加两张框架表的增量迁移（参考模板 `a8c42f910d37`），先在隔离库迁移和检查，再部署；不要拷贝模板的初始迁移去覆盖产品历史。独立的十万行强杀恢复样例见 `tests/framework/segment_sample.py` 和 `test_segmented_jobs.py`。

## 内置运维与非关键任务

APP_OPERATIONS 按配置开启备份、分段保留、容量和提醒，默认关闭，详见[内置运维](../operations/README.md)。旧的 JobPlan 默认 critical=True；明确允许"容量不足时延迟"的任务才加 critical=False。容量暂停只限制新领取，不取消在途的事务或批次；关键任务、备份、清理和提醒继续执行。pending 提醒只代表等待发送，不代表那个人已经收到。

## 多组织定时（2.2）

部署配置 `APP_SCHEDULE_ORG_IDS=["alpha","beta"]` 之后，同一个计划会分别为每个组织登记。旧的 `APP_SCHEDULE_ORG_ID=alpha` 仍然支持；两种配置同时填写时，旧编号必须包含在新列表里。模块的 `Schedule(org_ids=("alpha",))` 可以明确限定范围；`org_ids=()` 表示这是只运行一次的全局任务。没填组织的旧产品继续用原来的系统定时身份。组织不从门店或请求内容推断。去重键由计划、组织和时段共同确定，用元组摘要防止分隔符碰撞和超长键。升级前已登记的旧单组织时段，按原调用者组织复用，不会重复触发。

`Schedule(slot_input_field="request.window_end")` 可以把实际计划时段写进输入的 datetime 字段；任务的延迟和重试用同一份冻结的输入，不按执行当天重新选窗口。字段路径和组织在启动时检查。

## 固定来源导入与自动对账

`JobPlan(..., segmented=True, repeat_safe=True, import_plan=ImportPlan(...))` 复用分段事务。来源版本、范围键、实际目标与预期必须明确；队列自动按计划摘要去重，输入不同会拒绝重复键。最后一批 `checkpoint.finish` 之后、提交之前，框架自动读取目标表对账；短操作和未声明导入的任务不受影响。行数必须完全相等，合计精确相等，质量非空率达到最小值，非空引用必须存在。质量字段只统计 SQL 的非 NULL（空字符串是否算有效由产品规则决定）；空来源默认拒绝，确认是空集才声明 `allow_empty=True`。只需要核对行数时可以不声明其他指标，但没有登记的指标不代表已验证；金额用 ExactNumber/Decimal。

对账失败会让任务失败并撤销最后一批；已提交的批次保留。不能把恢复工具返回 0 当作导入成功。任务失败后，由产品核对来源和已提交的数据，再按原来的固定范围恢复；不要随意改计划的去重键重导。运行记录会持久化对账的实测值、预期值、是否通过与来源；还没到最后一批时，对账状态是未知。计算图显示对账节点，运行图和报告显示结果；配置 `APP_RUN_RECORDS=database` 保留跨进程证据。声明例子和接入步骤见[迁移 Skill](../../../.agents/skills/fastapi-template/references/product-migration.md)，独立双库样例见 `tests/framework/import_sample.py` 和 `test_import_ownership.py`。

## 第三代时间与排队

`ApplicationSpec.clock`或测试组装注入Clock。后台、流程、外部重试和执行记录沿用同一时钟，业务UTC时间与单调消耗分开。FakeClock只用于合成测试，生产组装拒绝它；运行记录标记时钟类别，模拟耗时不能当作实际性能。

`JobPlan(serial=SerialKey("conversation", "session_id"))`按组织与冻结输入的业务键跨worker串行。同一时刻的提交也保留数据库登记顺序；未知结果保留这个业务键的恢复顺序，后续任务不能越过它。只有明确处理了原任务，才能继续后面的任务。

`resources=(ResourceLimit("model", concurrency=4, cooldown=10),)`声明跨worker执行位置与执行间隔。领取使用短事务，资源用满或冷却时延后领取；完成、失败和等待重试归还位置，心跳只延长本次位置，旧租期不能复活。更改已登记资源额度先停止旧worker，等待在途位置结束，再用`uv run dev jobs resource model --capacity 4 --yes`明确调整；命令会拒绝在途资源和串行键，不能让不同worker各用不同额度。

`queue_timeout`限制首次执行前的排队预算，`attempt_timeout`限制一次尝试，`valid_until_field`读取输入中带时区的datetime。有效期冻结保存，每次领取与执行前再次核对；资源等待期间的过期任务也及时结束，不等到冷却结束。分段任务每批使用操作预算，明确声明attempt_timeout时还受整次尝试预算约束。

`revalidate=公开查询`使用同一输入、Validity输出，核对账户、版本或其他关键状态。查询必须登记，不能产生业务写入，并与后续业务共享本次预算。分段处理在每批执行前核对。身份和关键规则变化仍由产品查询说明，模板不会猜测产品业务。

明确的429等已确认等待使用`RetryLater(60, resource="model")`。资源必须在JobPlan声明；延后不消耗失败重试次数，也不占位置。已经产生外部写入的流程抛出RetryLater时仍转为未知，不能整项重发。旧任务没有新的失败计数时保留未知值，领取后按旧尝试语义接续，不在迁移里重发任务。

`uv run dev diagnose budgets`离线查看各类预算与调用位置；需要核对真实运行配置时明确加`--runtime-config`，只读配置，不连接数据库。调用配置超过上层期限时报告具体位置，排队预算、业务有效期与Pipeline长期等待不会被混为一次HTTP超时。

任务去重范围包含身份类型、身份编号和组织。旧的单身份键先核对冻结身份再复用，未知的旧任务不会因为升级键格式而被重复登记。服务密钥改变组织后，原任务不再按新组织执行。
