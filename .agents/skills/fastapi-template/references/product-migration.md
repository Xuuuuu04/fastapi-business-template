# 迁移旧业务

一次迁一项用户能检查、能使用的完整业务。例：经营日报 = 读取订单 → 计算 → 保存并发布 → 旧页面查看和下载。不整批搬函数，不把迁移变成全面重写。

## 开始一项业务

1. 读旧系统里这项业务的入口、调用关系、规则和样例，记下旧版本号。
2. 和用户确认：数据从哪来、应得什么结果、页面上有哪些操作、要哪些包和接口、做到什么算完成、这次不做什么。
3. 确认的规则写进业务文档（见 fastapi-business），再写成测试样例。

## 先搭整条链，再逐段实现

含定时或长流程的业务，先用 `new-pipeline` 搭出从定时入口到发布的整条链，再按阶段补来源、计算、保存和发布：

```bash
uv run dev new-pipeline report daily --title 经营日报 --stages collect,wait,calculate,publish --wait wait
```

短保存用普通操作，大批固定数据用分段任务，采集、等待、汇算、发布用多阶段流程，选法见 fastapi-module“选哪种执行方式”。不要先把底层包全做完才连流程，也不要把整段旧函数塞进一个阶段。

## 旧函数怎么处理

| 旧函数的情况 | 怎么处理 |
| --- | --- |
| 正确、独立，只接收数据返回结果 | 只迁当前业务用到的，放进 `calc/` 或 `steps/`，由正式步骤调用 |
| 查库、请求外部、计算、提交混在一起 | 拆开：读写库放 `store/`，外部调用放步骤（见 fastapi-module 框架用法“外部调用”），计算放 calc，保存交给框架的事务 |
| 重复、没用、这期不需要 | 不迁 |
| 已知有错，或拆开比重写还贵 | 和用户确认规则后，按确认的样例重写 |

旧数据库的表定义放 `server/legacy/`，用 `legacy.schema` 的 `legacy_metadata`，只通过存储构造参数 `legacy` 只读访问，不进新库的迁移。

## 导入数据和对账

固定来源的数据导入，在 module.py 的 JobPlan 上登记导入计划，最后一批提交前框架自动对账：

```python
import_plan = ImportPlan(
    source_revision="旧系统快照编号",
    key="门店A-20261008",
    reconcile=Reconcile(
        imported_rows,
        rows=10000,
        sums={"amount": Decimal("123456.78")},
        non_null={"quality": 1.0},
        references=(ImportReference("parent_id", parent_rows.c.id),),
        where=imported_rows.c.import_key == "门店A-20261008",
    ),
)
job = JobPlan(load, segmented=True, repeat_safe=True, import_plan=import_plan)
```

- 预期的行数、合计来自原件清单，不用导入后的数量反推。
- 对账不通过时任务失败并撤销最后一批，之前提交的批次保留，运行报告列出每个指标的预期和实测。
- 同一计划重复提交复用原任务，输入不同就拒绝。来源确实为空才写 `rows=0, allow_empty=True`。

## 比较新旧结果

- 用固定输入比较新旧输出，金额、单位、空值、边界、异常都要有明确预期。旧结果对不对，看确认过的业务规则。
- 用 `dev compare-api` 比较新旧两份接口文档。
- 接口对上了还要把旧页面真正接上，完成查看、下载这些操作。

## 记录和切换

每项业务按四个状态记在业务文档里：已实现、联合检查通过、旧页面可用、已正式切换。还没拿到真实数据来源或环境的写“未验证”。

迁移期间外部写操作只由一套系统执行。正式切换要用户单独确认；第一项业务可用之后，再扩大范围。
