# 内置运维

通过 `APP_OPERATIONS`（JSON）配置，默认全部关闭；旧的短操作、JobPlan 和 Schedule 的行为不变。开启后由 app/setup/build 挂载 `system_ops` 模块，所有功能都在 module.py 里登记 Contract、Flow、JobPlan 和 Schedule，worker 按系统全局的周期各运行一次；计算图和运行图里都能查到。

- backup（备份）：把数据库和正式文件归档到同一次备份，然后在新的库和新目录里恢复，比较所有表的行数、迁移版本、文件摘要，并调用真实应用的 `/health/ready`。只有验证成功才有 verified.json；失败的记录 verified=false 并登记 backup_failed。备份任务完成只说明“失败这个事实也保存下来了”，不等于备份可恢复。PostgreSQL 需要版本匹配的 pg_dump/pg_restore，以及在隔离恢复服务器上创建数据库的权限；只删除本次随机的 fastapi_restore 库，从不覆盖源库。SQLite 使用 backup API。
- retention（清理）：PR1 分段任务；固定截止，单段最多处理 batch_size 条，游标推进之后才提交下一段。清理的内容包括：已完成流程的成员、阶段和根，done/cancelled 的任务，运行记录、操作记录、临时上传，以及配置的原件前缀。unknown/blocked 的任务、活动或失败待处理的流程，以及关联的证据都保留。删除周期历史，意味着很早周期的去重证明也一起删除了，要按产品对历史的要求设置期限。
- capacity（容量）：实际观察磁盘使用率、PostgreSQL 整库大小（或 SQLite 文件加 WAL），超过阈值每天提醒一次。开启 pause_noncritical 时，跨 worker 暂停 JobPlan(critical=False) 的新领取；默认所有旧任务 critical=True，备份、提醒和清理仍是关键任务，在途的段不撤销。下一次检查发现容量恢复时自动解除暂停。检查失败时保留上次的暂停事实，不把未知当作正常。
- notifications（通知）：通用的 Channel 接口，已实现 Webhook；generic 直接发送 JSON，wecom/feishu 包装成机器人文本。逾期（PR2c 已入队）、任务的 unknown/blocked、备份失败、容量超阈值共用一张通知表。每次最多投递一条、锁定一条；HTTP 或平台拒绝的不标 sent，只记录 attempt 和错误类型。目标 URL 是 SecretStr，不进报告。发送保证至少一次，响应丢失或提交失败可能重复，通道接收方应按通知的业务 key 去重。

文件保留只删除明确的 `模块/原件目录` 前缀，绝不按 file_root 整体删除；配置之前先确认期限超过最长的等待和人工恢复时间。临时上传按 upload_days 清理；S3 按当前对象的时间删除，不删除历史版本。目录的符号链接不备份也不清理。S3 备份把当前对象下载到归档，恢复时校验到本地，不覆盖真实的桶；真实的 S3 凭据、网络和版本生命周期，仍需要在实际环境验证。

数据库的快照是一致的；文件和数据库之间不是跨系统的原子快照，manifest 里记录了开始和文件完成的时刻。重要的产品应该在“文件不可变键或对象版本”策略下运行，或在授权的静默窗口做备份；这个能力不能证明并发的文件修改和数据库引用一定一致。备份是敏感操作，目录权限和异地复制由部署负责。配置和验证命令见 deploy/backup.md。
