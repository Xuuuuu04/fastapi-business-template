# 备份与恢复

业务数据、任务表、操作记录和运行记录在 PostgreSQL 中。使用本地文件存储时，文件内容位于 Compose 的 `files` 卷；使用 S3 时位于对象存储。数据库备份必须与文件备份一起做恢复演练。

## 内置定时运维

`APP_OPERATIONS`配置JSON，功能独立开关、默认全部关闭。所有功能在框架module.py中登记定时任务，由worker执行，可从console/operations查看system_ops计算图和实际运行。

```dotenv
APP_OPERATIONS={"backup":true,"retention":true,"capacity":true,"notifications":true,"backup_root":"var/backups","backup_days":30,"backup_every_seconds":86400,"batch_size":500,"run_days":14,"job_days":30,"audit_days":90,"upload_days":7,"original_days":30,"original_prefixes":["report/originals"],"disk_percent":90,"database_bytes":10737418240,"pause_noncritical":true,"webhook_url":"https://实际提醒地址","webhook_format":"generic"}
```

- 示例前缀必须换成产品明确的原件目录；至少模块/目录两段，不配置就不删原件，不按file_root全删。保留期限应超过最长等待/人工恢复期限，先在隔离库/目录验收再开启。S3清理当前对象，历史版本由对象存储策略管理。
- PostgreSQL工具`pg_dump/pg_restore`不能低于服务器版本；Dockerfile带客户端。账号需要源表读取、快照导出和创建/删除本次随机恢复库权限。权限不足会明确备份失败，不会覆盖源库；部署账号可用专门受限运维环境，不应为了备份擅自扩大业务账号权限。
- 每次归档数据库与正式文件（本地或S3当前对象），新库/目录恢复并比较所有表行数、文件摘要，实际应用ready验证迁移版本。成功才写verified.json；失败保留manifest/归档以供定位、输出verified=false并登记backup_failed提醒，不清理旧可用备份。只按backup_days清理本框架verified归档；失败归档需人工核对后清理。
- 数据库一致快照与文件复制不是跨系统原子快照，manifest列时间范围。产品使用不可变文件键/版本策略或授权静默窗口，另外验证数据库引用对应文件；不能把摘要一致当跨系统业务一致。
- retention使用分段任务，每批<=batch_size；固定截止与游标，同批删除和提交证据一起保存。待确认任务、未完成/失败流程及关联证据不自动删。很早的完成流程周期证明会到期删除，产品需自行选择历史去重期限。不开启时保留原运行记录清理行为。
- 超容量每天登记一次提醒；暂停只影响显式JobPlan(critical=False)的下一次领取，旧任务默认关键。所有worker读取同一数据库暂停事实，容量恢复自动解除；在途事务/批次不撤销，检查失败不把未知当正常。
- Webhook通用JSON或wecom/feishu文本机器人，SecretStr目标不写报告；逾期/待确认/备份失败/容量告警共用通道。每次一条、有超时和响应预算，失败保持pending，平台拒绝也不标sent。至少一次，回执丢失可能重复，接收者按key去重。未配置/关闭notifications就只有pending，不代表人已收到。

## 怎样验证配置

先在授权隔离数据库和文件目录配置开启功能，执行迁移，再启动worker。不要在真实库用验收脚本导入样例或删除数据。

```bash
uv run alembic upgrade head
uv run python -m app.setup.worker
# 另一终端只读查看实际执行与提醒状态
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs list
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py diagnose runs
# 独立框架样例自动检查备份恢复/行数/迁移/ready/分段/暂停/提醒失败
uv run python -m pytest tests/framework/test_builtin_operations.py -q
```

检查归档verified.json、manifest行数/文件摘要和真实产物；在隔离目录放超期与未超期原件，确认只有配置前缀删除；把容量阈值设为测试库实际大小以下，确认非关键暂停而关键继续，再恢复阈值；Webhook指向获准的测试接收端，分别拒绝/成功并查pending/sent。真实S3、真实机器人、生产权限、镜像构建与异地恢复必须在目标环境另验，模板测试不代表已经部署。备份包含敏感业务，配置备份卷持久化、目录权限和异地复制（Compose的var卷包含默认var/backups）。

## 手工备份

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
