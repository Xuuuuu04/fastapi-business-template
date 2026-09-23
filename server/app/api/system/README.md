# system：系统接口

| 接口 | 用途 | 权限 |
| --- | --- | --- |
| GET /health/live | 进程是否存活 | 公开 |
| GET /health/ready | 数据库能否连通、结构是否已迁移到当前版本 | 公开 |
| GET /api/system/modules | 模块目录和模块关系图 | system.diagnostics |
| GET /api/system/flows/{操作名} | 操作的计算流程图和全部字段的来源 | system.diagnostics |
| GET /api/system/fields/{操作名}/{字段} | 逐层说明一个字段怎样得出 | system.diagnostics |
| GET /api/system/runs | 最近的运行和中文摘要，可按模块、状态、请求编号、任务编号筛选 | system.diagnostics |
| GET /api/system/runs/{运行编号} | 一次运行的全部记录（含下一层调用）和实际执行图 | system.diagnostics |
| GET /api/system/runs/{运行编号}/report | 中文诊断报告（Markdown） | system.diagnostics |
| GET /api/system/runtime | 内存、在途请求、连接池、运行记录缓冲、任务数量 | system.diagnostics |
| GET /api/jobs/{任务编号} | 查看自己登记的任务 | 登记者本人或 system.jobs |
| GET /api/system/jobs | 列出任务 | system.jobs |

这些接口只读。重新排队、取消任务等修改操作只能通过命令行 `tools.jobs` 进行，并要求 `--yes` 确认。
