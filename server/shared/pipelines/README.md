# 多阶段业务流程

在 `module.py` 声明 `Pipeline`、`Stage` 和 `Wait`。阶段引用已登记的公开后台操作；定时计划引用 `pipeline.start`，只登记首阶段。普通短操作保持原写法。

```python
pipeline = Pipeline(
    "prices.daily",
    "每日价格",
    Source,
    (
        Stage("choose", choose),
        Stage("collect", collect),
        Wait("upstream", poll, every=30, timeout=3600),
        Stage("publish", publish),
    ),
)
module = Module(..., pipelines=(pipeline,), jobs=(JobPlan(...), ...))
schedule = Schedule(
    ...,
    contract=pipeline.start,
    input=pipeline.start.input(request=StartRequest[Source](data=Source())),
    slot_input_field="request.period",
    org_ids=("org-a", "org-b"),
)
```

阶段输入默认来自上一阶段，首阶段来自初始输入；可以用 `input_from="input"` 或已完成阶段名。只能传声明的 `Data`，序列化上限 16 KiB，大结果传引用。分段阶段还需 `JobPlan(cursor=CursorData, segmented=True, repeat_safe=True)`，用于兼容性检查。

## 状态和恢复

`queued` 排队、`running` 执行、`waiting_external` 等待下次检查、`succeeded` 完成、`failed` 失败、`unknown` 外部结果待确认、`version_blocked` 后续格式变化暂停、`skipped` 跳过重叠周期、`cancelled` 取消。

同一个组织、同一个流程、同一个周期键只会登记一次。重叠周期怎么处理由 `overlap` 决定：默认的 `"skip"` 会跳过重叠的新周期并记下原因；`"queue"` 会让新周期在前一个周期结束后依次启动。各组织分别去重，互不影响。

成功的产出、阶段的成功状态和下一阶段的任务放在同一事务里提交。等待操作每次只执行一次，按间隔重新登记下一次检查的时间，超时就失败——不在操作里循环等上游；`max_parallel` 限制同一等待阶段跨组织的检查并发。等待阶段必须声明 `repeat_safe=True`。

`runtime.submit(pipeline.start, ...)` 返回的是流程编号，用流程查询接口查看；不要把它当成普通任务编号来用。

`operations pipelines list/show/resume` 与 `/system/console` 查看状态、阶段耗时、版本及运行记录。恢复只重新排队当前失败的那个阶段，前面阶段的产出和分段游标都保留。结果待确认的不会自动重做；人工核实确实没有产生效果之后，才能单独确认。

后续阶段的输入、输出、游标格式或声明发生变化时，流程会暂停；只是内部实现或模块版本变化的，继续执行，每段记录实际使用的版本。接受变化必须显式确认，且现有的输入和游标仍然要通过验证。

## 内部组织

- `plan/registration/schema`：声明、启动检查和格式摘要。
- `engine/runner/failure`：启动、短事务推进、失败与租约状态。
- `tables/storage`：两张框架表与有条件更新。
- `recovery/views`：人工恢复、摘要、阶段运行图。
- `gate`：执行器生成入口的事务工具。

四阶段独立样例在 `tests/framework/pipeline_sample.py`；不登记预置业务。


## 扇出和固定来源

```python
pipeline = Pipeline(
    "collect.daily",
    "采集后汇算",
    Begin,
    (
        Stage("select", select_sources, freeze_sources=True),
        FanOut(
            "requests",
            plan_requests,
            stages=(
                Stage("submit", submit_request, source=Sources),
                Wait("poll", poll_request, every=30, timeout=10800, max_parallel=8),
            ),
            join=All(),
            max_parallel=8,
        ),
        Stage("sum", calculate, source=Sources, members={"requests": Collected}),
    ),
)
```

规划操作在保存步骤里调用 `pipeline.add_members([Member(key=稳定键, input=已声明Data), ...])`。每批最多 1000 个成员，单个输入上限 16 KiB；规模很大的规划用 PR1 分段提交。规划完成之后才开始派发成员，同时在途的成员最多 `max_parallel` 个；队列满了由 worker 定时继续派发，不会挤满 `max_queued`。所有子阶段同样必须登记公开操作和 JobPlan。

首阶段设置 `freeze_sources=True` 会把选定的 Data 封存起来。后续阶段和成员阶段声明 `source=Sources`，通过 `await pipeline.source(Sources)` 读取封存的版本，不再查询新版本。成员的原始输入也不能同一个键换内容。

`All()` 要求全部成员成功。`Ratio(0.9, required=("必需成员键",))` 要求成功成员占到本批总数的比例，且必需成员都成功；达标时名单就固定下来，迟到的结果只记状态，不混进汇算。框架会等当前已启动的动作收尾后才进入下一阶段；出现任何未知的外部效果都会暂停，不能靠比例绕过去。

汇算阶段声明 `members={"requests": Collected}`，然后用 `await pipeline.results("requests", Collected, after=游标, limit=50)` 按页读取有界的 Data。大的产出只放引用。成员失败后，人工恢复只重排失败成员的当前子阶段；前面的子阶段、成功的成员和分段游标都保留。

运行图先显示成员状态计数，console成员页和 `operations pipelines members` 按键分页看细节、版本、运行号。独立200成员样例在 `tests/framework/fanout_sample.py`。


## 最晚完成和逾期

`complete_by=DailyTime(time(9,30), zone="Asia/Shanghai", days_after=0)` 按周期所在的当地日期计算并固定截止时间；夜里开始、次日完成的流程用 days_after=1。人工启动时 period 要带时区；省略的话，用登记时刻的当地日期。

默认的 `on_overdue="continue"` 会继续执行，只保留逾期的事实并登记 pending 通知。`"pause"` 会阻止下一阶段或下一批，当前批完整提交后才停下；在 console 或 operations 里人工继续，前面的产出和游标保留。未知的外部结果仍然单独处理，不能用“继续”绕过核实。通知只是进入了队列；本版没有配置投递，不能说已经发送。

`dev status --summary` 默认只读本机的运行摘要缓存并显示观察时间，没有缓存就标未知；`--runs` 会刷新数据库里的观察，此刻之后可能又发生了变化，所以缓存不等于实时状态。`--operation` 会列出这个操作在流程里的位置。
