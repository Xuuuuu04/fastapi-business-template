# flow：步骤、流程与执行器

耗时同步计算使用 `heavy=True`，只接受 `data`。`APP_HEAVY_CONCURRENCY` 默认每进程 4 个实际工作；等待准入沿用操作期限，请求取消不提前归还线程额度，真实工作结束后才释放，尚未开始的取消计算会跳过。停止服务会唤醒并拒绝等待准入的调用。同步函数无法安全强制停止，计算自身必须有限结束；需要硬停止的任务应使用进程或独立计算服务及相应资源限制。

## 先选执行方式

| 方式 | 什么时候用 | 简短示例 |
| --- | --- | --- |
| 普通操作 | 短计算/短保存，结果必须一次成功或一起回滚 | 修改一条联系人：`Flow("修改", work=Work, result="result", steps=[validate, save])`，save声明saves=True |
| 分段提交 | 固定输入范围内批量处理，各批可以独立生效，要保留游标继续 | 十万行解析：`JobPlan(parse, segmented=True, repeat_safe=True, cursor=Cursor)`；每批5000行，保存后checkpoint.advance，下批继续 |
| 多阶段流程 | 采集、等待、汇算、发布等各有事务/失败恢复点，不能一次持有事务等待 | `Pipeline("report.daily", "日报", Begin, (...))`实际写法见下方：每个Stage引用公开操作，Wait只检查一次，不在步骤里sleep循环 |

Pipeline需要标题和明确输入Data，例如：

```python
daily = Pipeline(
    "report.daily",
    "经营日报",
    Begin,
    (
        Stage("collect", collect),
        Wait("wait", check_ready, every=30, timeout=3600),
        Stage("calculate", calculate),
        Stage("publish", publish),
    ),
)
# 在module.py登记pipelines=(daily,)，各阶段仍登记provides/jobs。
# calculate内部若处理很多行，可同时声明分段JobPlan与Cursor。
```

这些是已定义操作的登记片段，不代替Data/步骤实现。普通操作保持原写法；Pipeline不能把一段长函数包成Stage就算完成，应拆出独立事务边界；阶段数据<=16KiB，大正文传原件/结果引用。完整独立样例：tests/framework/drill_sample.py（定时→采集→等待→分段解析→汇算→CSV），分段恢复见jobs README，多阶段/扇出/截止见[流程说明](../pipelines/README.md)。

## 开发者写法

```python
# 计算应付金额
@step("计算应付", reads=["subtotal", "discount"], writes=["total"], rule="R-04")
def count_total(data: QuoteWork) -> None:
    data.total = data.subtotal - data.discount
```

- `reads`、`writes`：只能读写声明的字段，越界、类型不对、声明要写却没写都会报错并指出步骤和字段。
- 参数名决定步骤能拿到什么：`data`、`store`、`call`、`model`、`remote`、`cache`、`emit`、`later`、`caller`、`note`。只有 `data` 的步骤是纯计算。
- 一个步骤只做一类事：`store`、`call`、`model`、`remote` 最多出现一个。
- 写数据库的步骤要加 `saves=True`；其他步骤拿到的数据库连接是只读的。
- 需要等待的步骤写 `async def`；耗时的纯计算加 `heavy=True` 放进线程。
- 步骤不 `return` 结果，结果写到 `data` 的字段上。
- 上游协议由Module.endpoints登记、步骤endpoints声明；直接或经store调用均用同一权限范围。
- 外部系统由模块声明，使用它的步骤还需写 `remotes=[...]`。写入事务开始后不能再调用外部接口。
- 流式操作声明 `stream=True`，异步步骤通过 `emit` 输出分段；客户端断开会取消运行并回滚。
- 流式输出最多缓冲 16 条事件。客户端断开后等待运行清理，不向无人消费的队列再写结束标记。

## 文件

| 文件 | 内容 |
| --- | --- |
| [step.py](step.py)、[flow.py](flow.py) | 步骤、条件、流程的声明 |
| [checks.py](checks.py) | 流程的启动检查：字段来源、写入者唯一、参数与声明一致、保存后不再调大模型 |
| [view.py](view.py) | 步骤看到的数据 StepView，负责读写限制和类型校验 |
| [inject.py](inject.py) | 按参数名准备 store、call、model、remote、cache、emit 等 |
| [runner.py](runner.py) | 按顺序执行步骤并记录 |
| [runtime.py](runtime.py) | 执行器入口：权限、超时、事务提交与回滚、模块之间的调用 |
| [streaming.py](streaming.py)、[auditing.py](auditing.py) | 流式事件与操作记录与事务衔接 |
| [scope.py](scope.py) | 一次运行共用的事务和剩余时间 |
| [testing.py](testing.py) | `try_step`：在测试中单独运行一个步骤 |

## 事务怎样安排

第一个 `saves=True` 的步骤开始写入事务；本次运行和它调用的其他模块共用这个事务；最外层操作成功时提交，任何一步失败都回滚。提交时连接断开，报告“结果待确认”，不声称已回滚。写入事务开始后不能再调用大模型，避免长时间占用连接。

## 先读后写时怎样保证一致

写入事务开始前的读取步骤使用单独的只读连接，读到的是当时的数据；到保存时，别的请求可能已经改过。
结果只用于展示或说明时可以接受；**要按读到的值决定写入**（扣库存、扣余额、状态流转）时，二选一：

| 做法 | 写法 |
| --- | --- |
| 在保存步骤里加锁读取 | 读取放进 `saves=True` 的步骤，用 `db.first_for_update(select(...))`；只读步骤调用会报错 |
| 带条件更新 | `db.change_or_fail(update(...).where(表.c.状态 == 读到的状态), 业务错误())`：一行都没改到时抛出这个业务错误 |

不要在只读步骤里读、再在后面的保存步骤里无条件写入。

可复用的纯计算放在可选 calc/，步骤 calcs=[函数] 声明直接调用。calc 只接收参数并返回值；步骤依旧写 data，耗时包括所有calc调用。
