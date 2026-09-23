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
