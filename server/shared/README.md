# shared：框架

这里放所有业务模块共用的框架：模块注册、流程执行、事务、运行记录、任务、大模型入口等。开发业务时一般不需要改这里；这里的改动属于框架改动，受 `framework.lock` 保护，需要单独审查。

## 业务代码只导入 shared.public

业务模块（`service/`）只能从 [public.py](public.py) 导入框架功能，不直接导入 `shared` 下的其他文件。这样做的原因：业务代码和框架内部实现解耦之后，框架内部可以随意修改而不影响业务；质量检查也能简单地判断依赖有没有越界。

| 名称 | 用途 |
| --- | --- |
| `meaning` | 写字段的中文含义、单位、规则编号、空值含义 |
| `Data`、`WorkData`、`Page`、`CursorPage`、`Nothing` | 公开数据、流程数据、按条数分页结果、按位置续读结果、空结果 |
| `contract` | 在模块的 public.py 中声明对外操作 |
| `step`、`condition`、`Flow` | 写步骤、条件，并把步骤连成流程 |
| `Module` | 在 module.py 中声明模块 |
| `Call`、`Model`、`Later`、`Note`、`Caller`、`Db` | 步骤参数的类型：调用其他模块、大模型、登记任务、数据说明、调用者、数据库 |
| `remote`、`RemoteClient`、`ModuleCache`、`ModuleFiles` | 声明外部系统，使用外部接口、缓存与文件存储 |
| `Emitter`、`org_column`、`owner_column` | 流式输出的步骤参数、按组织隔离的表列、按负责人隔离的表列（行级权限） |
| `Vault` | 存储实现的构造参数 `vault`：字段加密 |
| `JobPlan`、`Retry`、`Schedule` | 后台任务和定时计划 |
| `prompt` | 声明提示词 |
| `BusinessError`、`Kind` | 业务错误 |
| `metadata`、`UtcTime`、`ExactNumber` | 在 store/tables.py 中定义表 |

## 目录

| 目录 | 负责 |
| --- | --- |
| [data](data/) | 字段说明和两类数据的基类 |
| [modules](modules/) | 操作约定、模块声明、启动检查、模块目录 |
| [flow](flow/) | 步骤、条件、流程，以及执行器 |
| [db](db/) | 连接池、只读连接与写入事务、给 store 用的 Db |
| [records](records/) | 运行记录、中文摘要、记录的保存位置 |
| [graphs](graphs/) | 模块关系图、流程图、字段来源、实际执行图和排查报告 |
| [jobs](jobs/) | 任务表、worker、定时计划 |
| [model_calls](model_calls/) | 大模型调用入口 |
| [remote_calls](remote_calls/) | 外部接口连接、重试、连续失败后暂停调用和调用记录 |
| [cache](cache/) | 进程内和 Redis 缓存 |
| [files](files/) | 本地和 S3 兼容文件存储、上传临时区 |
| [exchange](exchange/) | 导入导出用的 CSV、Excel 读写 |
| [telemetry](telemetry/) | OpenTelemetry 跨度导出 |
| [access](access/) | 调用者身份、权限、服务密钥、令牌、操作记录和字段加密 |
| [errors](errors/) | 错误种类和框架错误 |
| [config](config/) | 运行配置 |
| [logs](logs/) | 日志格式 |

## 依赖方向

`shared` 不导入 `app`、`service`、`tools`。框架需要的外部能力（例如登记任务）用约定表示，由 `app/setup` 在启动时把具体实现接进来。
