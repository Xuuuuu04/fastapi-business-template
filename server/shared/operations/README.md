# 内置运维

配置 `APP_OPERATIONS`（JSON）。默认全部关闭，旧短操作、JobPlan和Schedule不改行为。开启后由app/setup/build挂载`system_ops`，所有功能在module.py登记Contract、Flow、JobPlan、Schedule，worker按系统全局周期运行一次；计算图和运行图可查。

- backup：数据库与正式文件同次归档，随后新库/新目录恢复，比较所有表行数、迁移版本、文件摘要和真实应用`/health/ready`。只有验证成功才有verified.json；失败结果verified=false并登记backup_failed。备份任务完成只代表失败事实也保存成功，不等于备份可恢复。PG需要匹配服务器版本的pg_dump/pg_restore及在隔离恢复服务器创建数据库的权限；只删除本次随机fastapi_restore库，从不覆盖源库。SQLite使用backup API。
- retention：PR1分段任务；固定截止，单段最多batch_size，游标推进后再提交下一段。清理已完成流程的成员/阶段/根、done/cancelled任务、运行记录、操作记录、临时上传和配置原件前缀。unknown/blocked任务、活动/失败待处理流程以及关联证据保留。删除周期历史意味着很早的周期去重证明也删除，需按产品历史要求设置期限。
- capacity：磁盘使用率/PG整库大小或SQLite文件+WAL实际观察，超阈值每天一次提醒。pause_noncritical开启时跨worker暂停JobPlan(critical=False)的新领取；默认所有旧任务critical=True，备份/提醒/清理仍关键，在途段不撤销。下一次检查容量恢复自动解除。检查失败保留上次暂停事实，不把未知当正常。
- notifications：通用Channel接口，Webhook已实现；generic发送JSON，wecom/feishu包装机器人文本。逾期（PR2c已入队）、任务unknown/blocked、备份失败、容量超阈值共用通知表。每次最多投递一条、锁一条，HTTP/平台拒绝不标sent，记录attempt与错误类型。目标URL为SecretStr，不进入报告。至少一次发送，响应丢失或提交失败可能重复，通道接收者应按通知业务key去重。

文件保留只删除明确`模块/原件目录`前缀，绝不按file_root整体删除；配置前先确认期限超过最长等待/人工恢复时间。临时上传按upload_days；S3按当前对象时间删除，不删除历史版本。目录符号链接不备份/清理。S3备份下载当前对象到归档，恢复校验到本地，不覆盖真实桶；真实S3凭据、网络、版本生命周期仍需环境验证。

数据库快照一致；文件与数据库不是跨系统原子快照，manifest记录开始/文件完成时刻。重要产品在文件不可变键/对象版本策略下运行，或在授权静默窗口备份；此能力不证明并发文件修改与数据库引用一定一致。备份敏感，目录权限与异地复制由部署负责。配置和验证命令看deploy/backup.md。
