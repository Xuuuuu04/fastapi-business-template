# db：数据库连接与事务

## 负责

- [database.py](database.py)：连接池；只读连接（PostgreSQL 用只读事务，SQLite 用 query_only）；写入事务；判断数据库暂时不可用。
- [access.py](access.py)：给 store 使用的 `Db`，只能执行语句，没有提交、回滚、关闭方法。先读后写时用 `change_or_fail`（带条件修改，一行没改到就报业务错误）或 `first_for_update`（在保存步骤中加锁读取）。
- [tables.py](tables.py)：全项目共用的 `metadata`，约束命名固定。
- [types.py](types.py)：`UtcTime`（带时区的时间，读出一律 UTC）和 `ExactNumber`（精确小数）。在 SQLite 和 PostgreSQL 上行为一致。
- [schema.py](schema.py)：读取数据库当前的迁移版本，供就绪检查使用。
- [org.py](org.py)：按组织隔离的表列与语句检查；复杂语句无法证明隔离条件时拒绝执行。

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
