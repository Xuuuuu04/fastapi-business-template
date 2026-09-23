# 备份与恢复

业务数据、任务表和运行记录都在 PostgreSQL 中。备份只有在恢复演练成功后才算可用。

## 备份

```bash
# 在数据库所在机器上执行，生成带日期的压缩备份
docker compose -f deploy/compose.yaml --env-file .env exec -T database \
  pg_dump -U app -d app --format=custom > backup-$(date +%Y%m%d-%H%M).dump
```

- 建议每天备份一次，备份文件复制到另一台机器或对象存储，按保留期限清理。
- 备份文件包含业务数据，按敏感数据保管。

## 恢复演练

```bash
# 在一个空的测试数据库上恢复，不要直接覆盖生产数据库
createdb -h 测试库地址 -U app app_restore
pg_restore -h 测试库地址 -U app -d app_restore --no-owner backup-日期.dump
```

恢复后核对：`alembic_version` 与代码版本一致；主要业务表的行数与备份时相近；用恢复出的库启动一次服务，`/health/ready` 返回 ready。

## 回退代码

代码回退不代表数据库可以安全回退。迁移只增加不删除时，旧代码通常可以运行；有删除列或改类型的迁移，回退前必须先确认数据影响，必要时用备份恢复。
