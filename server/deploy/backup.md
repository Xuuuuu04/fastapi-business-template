# 备份与恢复

业务数据、任务表、操作记录和运行记录在 PostgreSQL 中。使用本地文件存储时，文件内容位于 Compose 的 `files` 卷；使用 S3 时位于对象存储。数据库备份必须与文件备份一起做恢复演练。

## 备份

```bash
# 在数据库所在机器上执行，生成带日期的压缩备份
docker compose -f deploy/compose.yaml --env-file .env exec -T database \
  pg_dump -U app -d app --format=custom > backup-$(date +%Y%m%d-%H%M).dump
```

- 建议每天备份一次，备份文件复制到另一台机器或对象存储，按保留期限清理。
- 备份文件包含业务数据，按敏感数据保管。
- 本地文件存储还需备份 `files` 卷中的 `files/` 目录，并记录与数据库备份对应的时间点；`uploads/` 是临时区，可以单独按保留规则处理。S3 存储应开启对象存储自己的备份或版本策略。

## 恢复演练

```bash
# 在一个空的测试数据库上恢复，不要直接覆盖生产数据库
createdb -h 测试库地址 -U app app_restore
pg_restore -h 测试库地址 -U app -d app_restore --no-owner backup-日期.dump
```

恢复后检查：`alembic_version` 与代码版本一致；主要业务表的行数与备份时相近；文件记录对应的对象可以下载；用恢复出的库启动一次服务，`/health/ready` 返回 ready。

## 回退代码

代码回退不代表数据库可以安全回退。迁移只增加不删除时，旧代码通常可以运行；有删除列或改类型的迁移，回退前必须先确认数据影响，必要时用备份恢复。
