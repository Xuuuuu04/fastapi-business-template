# db：数据库连接与事务

## 负责

- [database.py](database.py)：连接池；只读连接（PostgreSQL 用只读事务，SQLite 用 query_only）；写入事务；判断数据库暂时不可用。
- [access.py](access.py)：给 store 使用的 `Db`，只能执行语句，没有提交、回滚、关闭方法。先读后写时用 `change_or_fail`（带条件修改，一行没改到就报业务错误）或 `first_for_update`（在保存步骤中加锁读取）。
- [tables.py](tables.py)：全项目共用的 `metadata`，约束命名固定。
- [types.py](types.py)：`UtcTime`（带时区的时间，读出一律 UTC）和 `ExactNumber`（精确小数）。在 SQLite 和 PostgreSQL 上行为一致。
- [schema.py](schema.py)：读取数据库当前的迁移版本，供就绪检查使用。
- [org.py](org.py)：按组织隔离的表列与语句检查；复杂语句无法证明隔离条件时拒绝执行。
- [owner.py](owner.py)：按负责人隔离（行级权限）：`owner_column(see_all="权限名")`，没有这个权限的调用者每层查询都要写 `owner_id == caller.id`，检查方式与组织隔离相同。
- [history.py](history.py)：数据变更历史。`db.update_tracked(表, 条件, 值)` 修改时把前后不同的字段写进 `system_change_history`，与修改同一事务；列加 `info={"secret": True}` 时只记“已隐藏”。查询接口 `/api/system/changes`。
- [tracing.py](tracing.py)：通过 `Db` 执行的 SQL 和变更历史写入记录耗时、结果行数、表或视图、调用函数及行号；旧库也记录。失败原样抛出，不保存 SQL 文本、参数或结果。标量查询的行数保持未知。时间包含权限检查和结果读取，属于步骤时间的一部分，不与步骤时间相加。
- 数据量大的列表用 `db.page_after(查询, 唯一可排序的列, after, limit)` 按位置续读，返回 `CursorPage`。

## 规则与原因

| 规则 | 原因 |
| --- | --- |
| store 只拿到 `Db`，不能自己提交 | 事务由最外层操作统一提交或回滚，子模块不能提前提交 |
| 没有 `saves=True` 的步骤拿到只读连接 | 在数据库层面阻止“读取”步骤偷偷写入 |
| 数据访问用 SQLAlchemy Core，不用 ORM 对象 | async 下 ORM 的延迟加载容易出错；显式 SQL 也便于审查 |
| 时间必须带时区 | 不同服务器时区不同，不带时区的时间会被误解 |
| 金额用 `ExactNumber` | 浮点数有误差 |
| 服务启动时不自动迁移 | 多个实例同时迁移会冲突，迁移只在部署步骤执行 |
| 按组织隔离的表用 `org_column()`，查询条件明确限定调用者组织 | 漏掉组织条件时直接报错，阻止跨组织读取或修改 |

组织条件按每一层查询分别检查：子查询、表别名、更新语句关联的表都要写自己的组织条件，只在最外层写一次不够。例如统计本组织文件数的子查询要写成：

```python
count = select(func.count()).select_from(files).where(files.c.org_id == caller.org_id)
rows = await db.all(
    select(files.c.id, count.scalar_subquery()).where(files.c.org_id == caller.org_id)
)
```

组织条件只认 `列 == 值` 的写法；`in_`、`or_` 中缺组织条件的分支、无法判断的复杂语句都会被拒绝，改成简单语句即可。

迁移旧系统时，存储实现通过 `legacy` 构造参数得到独立只读库，旧表用 `legacy_metadata` 声明，参见 [旧系统迁移](../../legacy/README.md)。业务数据库入口拒绝原始 SQL 文本，以免绕过组织条件检查。

预期可能失败的写入（例如唯一约束冲突）放在 `db.savepoint()` 中执行，失败时只撤销这一段，再转成业务错误。

每步骤最多保留 200 次 SQL 的细节，超出仍统计次数与总用时并标明不完整。表名从 SQLAlchemy 表声明取得，
视图用 `Table` 声明时同样显示名称；旧库原始 SQL 的表名保持未知。连接取得和事务管理时间包含在步骤或操作总时间中，
框架内部的认证、队列、运行记录保存不伪装成业务 SQL。测试/演练可选择附安全的 EXPLAIN 摘要，见下方。

## 产品自己的 PostgreSQL 行级策略

可选配置 `APP_DATABASE_ORG_SETTING=product.org_id`。框架在每个业务语句之前，把可信调用者的组织绑定到当前事务的这个设置上；连接被复用或组织切换时会重新绑定。空组织和 `*` 不会扩大 RLS 权限。默认不绑定任何设置，SQLite 保持原来的行为。策略、强制 RLS 和应用角色的权限由产品的迁移明确创建；不能因为配置了这个字段，就认为数据库策略或角色已经验证过。

例如产品的策略可以读取 `current_setting('product.org_id', true)`。
业务域的名称、对象大小、小数精度与比率边界归业务包的`store/`和迁移所有，不进入通用模板。
已有产品可以保留自己的域类型适配，再按产品升级说明迁出共享框架。

[ownership.py](ownership.py) 收集明确表归属并保护迁移，登记与旧产品升级见 [迁移说明](../../migrations/README.md)。

## 操作查询额度

从 `shared.public` 导入 `QueryBudget`，在公开约定声明：

```python
read = contract(
    "goods.read",
    "读取商品",
    input=ReadInput,
    output=ReadOutput,
    access="goods.read",
    query_budget=QueryBudget(queries=20, rows=5000, bytes=64000, repeated=20),
)
# module.py仍在provides里登记read和Flow，不另建一份额度配置。
```

- 额度按一次操作运行累计（分段任务按每批累计），包括同步调用的子操作；后台任务另行计算。queries 是通过 Db 执行的 SQL 次数，rows 是返回或修改的行数；框架内部的队列、认证和记录保存不算进业务额度。
- bytes 是返回列内容的大小：文本按 UTF-8 计算，二进制按长度计算，普通标量按文字长度计算，JSON 字典和列表逐项累计内容（不计容器的语法字符），嵌套超过 32 层的保持未知。它不代表数据库的网络流量，也不代表 Python 对象的内存；写入不计入返回内容。scalar 查询的行数、无法识别的列类型大小、失败的查询结果都保持未知。未知的次数和已测的总量分开列出，不能拿未知的东西说符合额度。
- 同一个文件或存储函数的累计调用超过 repeated 时，提示“疑似在循环里逐行查询”；不同 SQL 的调用行合并计数。每步最多保留 200 条 SQL 细节和 200 种函数累计，超出的部分仍然累计总次数、行数和大小，只是函数定位明确标“不完整”；子操作的位置也最多 200 种。
- 没有声明的操作使用宽松的默认额度：1000 次 SQL、100000 行、64000000 字节、同一函数 100 次，超了只警告，旧操作不需要改代码。显式声明之后，APP_ENV=test 默认超额即失败，检查在事务提交前执行并回滚；生产环境永远只记录，不改变业务结果。
- `APP_QUERY_BUDGET_MODE=warn` 让测试环境只警告；`error` 在测试环境连未声明的操作也按默认额度判失败，用在产品逐项迁移完成之后收紧约束。默认是 auto。本地环境只警告。
- `APP_QUERY_BUDGET_EXPLAIN=true` 只在 APP_ENV=test 的 PostgreSQL 上生效；对已超额的查询，每步最多保存三份执行计划，而且只对不含加锁的 SELECT。使用 EXPLAIN 而不是 ANALYZE；只保存节点、表、估计行数、宽度和成本，不保存 SQL、Filter 和参数。诊断失败标未知，不改变业务事务。
- 运行结束后的 query_budget 写进运行 JSON、运行图和中文报告；计算图和启动校验读取同一份约定。dev status --operation 显示额度和最近一次测试的实测结果、源码是否还是当前版本，没测过显示未知；drill 的每个阶段列出各次运行的 query_budgets。默认不查询业务数据库。

这是运行结束后的检测，不是读取时的硬性截断或 SQL 超时；巨大的查询仍可能先耗尽资源。请用 Db.page_after 或批量查询控制读取量；数据库自己的语句超时和索引，仍要按产品实际情况验证。没有新增的数据库迁移。

## 固定范围批插

`Db.insert_many(table, rows)` 使用 SQLAlchemy 的标准 INSERT 参数列表和 RETURNING，让受支持的 SQLite/PostgreSQL 通过 insertmanyvalues 执行一条批量 SQL，并复用编译结果。每次最多 100 行，且这些行的字段集合要相同；另外还按数据库页面和最大参数数限制。不支持的数据库会明确报错，不会退回逐行写入。省略的字段仍然逐行执行列默认值。

执行前仍然逐行检查组织和负责人；只读步骤不能调用。事务由原来的流程管理。运行记录只记一次实际 SQL、真实修改的行数和耗时；RETURNING 的常量只用来确认行数，不暴露业务数据。产品存储自己按字段集合分批；这里不做提交，也不处理业务错误。
