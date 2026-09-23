# 公共功能

本层按明确能力分类，禁止新增用途不清楚的 utils 或 common 子包。一个能力有多个调用方、职责不属于具体业务时才放在这里。

| 目录 | 作用 |
| --- | --- |
| [config](config/README.md) | 配置读取和检查 |
| [db](db/README.md) | 连接、会话、事务工具及集中迁移文件 |
| [login](login/README.md) | 身份与会话检查 |
| [logs](logs/README.md) | 运行情况、请求与任务关联记录 |
| [files](files/README.md) | 文件保存、读取和清理机制 |
| [jobs](jobs/README.md) | 后台执行、定时、进度和恢复机制 |
| [history](history/README.md) | 记录业务提供的重要操作事实 |
| [notices](notices/README.md) | 通知记录与发送机制 |

这里不计算报表、不决定订单权限，也不导入具体业务服务。业务规则留在 service；公共能力需要调用业务时，由 app/setup 注册约定的处理函数。

shared/db/migrations 是部署时执行的结构变更文件，虽然归档在此，运行时数据库工具不导入或自动执行它们。业务表定义依然属于对应业务的 store。

这些能力的细节各自独立，进入 shared 后再选择需要的部分。当前仍为设计目录。
