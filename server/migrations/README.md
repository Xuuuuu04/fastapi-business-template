# migrations：数据库结构迁移

使用 Alembic。连接地址与服务相同（`APP_DATABASE_URL`），表结构从 `app/setup/catalog.py` 登记的模块收集。

```bash
uv run alembic upgrade head                                   # 迁移到最新版本（部署步骤执行）
uv run alembic revision --autogenerate -m "add xxx tables"    # 新增或修改表之后生成迁移
```

- 生成迁移前本地数据库必须先升级到最新版本，否则 Alembic 报“Target database is not up to date”。
- 生成的迁移文件必须人工检查后再提交；删除列、删除表会删除数据，要先确认。
- 服务启动时不自动迁移；`/health/ready` 会检查数据库版本是否与代码一致。
- 架构测试会对比迁移后的结构与代码中的表定义，漏写迁移会失败。

初始迁移 `7e03c1a0b624` 仅创建公共框架表，供新项目空数据库使用。已有项目保留自己的迁移历史，不直接替换模板迁移；此次精简没有访问或修改现有数据库。

## 表的归属与旧产品接入

框架表自动登记；业务表必须在模块 `tables` 中登记（从模块自己的 tables.py 导入）。
需要修改或删除已不在metadata中的历史表，在 module.py 的 `owned_tables=("old_table",)`
或产品配置 `APP_OWNED_TABLES=["old_table"]` 登记。仅保留的外部/历史表用
`external_tables` 或 `APP_EXTERNAL_TABLES` 登记，自动生成迁移将忽略它们，不能修改它们。
含schema时写 `schema.table`。同一表不能同时归 owned 和 external。
关闭模块入口仍收集该模块全部表，不会自动生成删除。

自动生成时遇到未登记表，一律拒绝并指出表名与登记方法，不通过兼容模式放行。
启动和完整检查扫描已有迁移的 drop/rename/alter/drop-column，包括批量操作与原始SQL。
旧产品默认警告；逐条整理已有历史表归属、将原始SQL改为可检查的Alembic声明后，
开启 `APP_MIGRATION_STRICT=true` 把警告升级为错误。扫描不执行源码，动态表名/原始SQL
的归属为未知，严格模式拒绝；它不能证明自定义Python函数中任意SQL安全，迁移仍需人工审查。
已有产品保留原迁移链，不覆盖初始迁移。本能力无新增框架表。
