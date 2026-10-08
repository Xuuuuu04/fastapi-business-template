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
# Module(..., pipelines=(pipeline,), jobs=(JobPlan(...), ...))
# Schedule(..., contract=pipeline.start,
#   input=pipeline.start.input(request=StartRequest[Source](data=Source())),
#   slot_input_field="request.period", org_ids=("org-a", "org-b"))
```

阶段输入默认来自上一阶段，首阶段来自初始输入；可以用 `input_from="input"` 或已完成阶段名。只能传声明的 `Data`，序列化上限 16 KiB，大结果传引用。分段阶段还需 `JobPlan(cursor=CursorData, segmented=True, repeat_safe=True)`，用于兼容性检查。

## 状态和恢复

`queued` 排队、`running` 执行、`waiting_external` 等待下次检查、`succeeded` 完成、`failed` 失败、`unknown` 外部结果待确认、`version_blocked` 后续格式变化暂停、`skipped` 跳过重叠周期、`cancelled` 取消。

同一组织、流程、周期键只登记一次。`overlap="skip"` 默认跳过重叠新周期并记原因；`"queue"` 在前周期结束后依次启动。组织分别去重，不互相影响。

成功产出、阶段成功和下一任务在同一事务提交。等待操作每次执行一次，按间隔重新登记检查时间，超时失败，不在操作内循环等上游；`max_parallel` 限制同一等待阶段跨组织的检查并发。等待阶段必须声明 `repeat_safe=True`。

`runtime.submit(pipeline.start, ...)` 返回流程编号，使用流程查询接口查看，不把它当作普通任务编号。

`operations pipelines list/show/resume` 与 `/system/console` 查看状态、阶段耗时、版本及运行记录。恢复只重新排队当前失败阶段，前面的产出和分段游标保留。结果待确认不自动重做；人工核实没有产生效果后才能单独确认。

后续阶段的输入、输出、游标格式或声明变化会暂停；内部实现和模块版本变化继续执行，每段记录实际版本。接受变化必须显式确认且现有输入和游标仍能通过验证。

## 内部组织

- `plan/registration/schema`：声明、启动检查和格式摘要。
- `engine/runner/failure`：启动、短事务推进、失败与租约状态。
- `tables/storage`：两张框架表与有条件更新。
- `recovery/views`：人工恢复、摘要、阶段运行图。
- `gate`：执行器生成入口的事务工具。

四阶段独立样例在 `tests/framework/pipeline_sample.py`；不登记预置业务。逾期通知在后续版本提供。


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

规划操作在保存步骤里调用 `pipeline.add_members([Member(key=稳定键, input=已声明Data), ...])`。每批最多1000个，单个输入上限16 KiB；大规模规划用PR1分段提交。规划完成后才派发成员，最多 `max_parallel` 个在途成员；队列满了由worker定时继续，不挤满 `max_queued`。所有子阶段同样必须登记公开操作和JobPlan。

首阶段 `freeze_sources=True` 把选定Data封存。后续及成员阶段声明 `source=Sources`，通过 `await pipeline.source(Sources)` 读取，不查询新版本。成员的原始输入也不能同键换内容。

`All()` 要求全部成功。`Ratio(0.9, required=("必需成员键",))` 要求成功占本批总数的比例以及必需成员成功；达标时固定纳入名单，迟到结果只记状态，不混入汇算。框架等当前已启动动作收尾后才进入下一阶段；任何未知外部效果都暂停，不能用比例绕过。

汇算阶段声明 `members={"requests": Collected}`，再用 `await pipeline.results("requests", Collected, after=游标, limit=50)` 读取有界Data页。大产出只放引用。成员失败后人工恢复仅重排失败成员当前子阶段，前面的子阶段、成功成员及分段游标都保留。

运行图先显示成员状态计数，console成员页和 `operations pipelines members` 按键分页看细节、版本、运行号。独立200成员样例在 `tests/framework/fanout_sample.py`。
