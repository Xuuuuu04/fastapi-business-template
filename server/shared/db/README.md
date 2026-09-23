# db：数据库连接与事务

## 负责

- [database.py](database.py)：连接池；只读连接（PostgreSQL 用只读事务，SQLite 用 query_only）；写入事务；判断数据库暂时不可用。
- [access.py](access.py)：给 store 使用的 `Db`，只能执行语句，没有提交、回滚、关闭方法。
- [tables.py](tables.py)：全项目共用的 `metadata`，约束命名固定。
- [types.py](types.py)：`UtcTime`（带时区的时间，读出一律 UTC）和 `ExactNumber`（精确小数）。在 SQLite 和 PostgreSQL 上行为一致。
- [schema.py](schema.py)：读取数据库当前的迁移版本，供就绪检查使用。

## 规则与原因

| 规则 | 原因 |
| --- | --- |
| store 只拿到 `Db`，不能自己提交 | 事务由最外层操作统一提交或回滚，子模块不能提前提交 |
| 没有 `saves=True` 的步骤拿到只读连接 | 在数据库层面阻止“读取”步骤偷偷写入 |
| 数据访问用 SQLAlchemy Core，不用 ORM 对象 | async 下 ORM 的延迟加载容易出错；显式 SQL 也便于审查 |
| 时间必须带时区 | 不同服务器时区不同，不带时区的时间会被误解 |
| 金额用 `ExactNumber` | 浮点数有误差 |
| 服务启动时不自动迁移 | 多个实例同时迁移会冲突，迁移只在部署步骤执行 |

预期可能失败的写入（例如唯一约束冲突）放在 `db.savepoint()` 中执行，失败时只撤销这一段，再转成业务错误。
