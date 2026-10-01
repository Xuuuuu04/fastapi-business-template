# system：系统接口

| 接口 | 用途 | 权限 |
| --- | --- | --- |
| GET /health/live | 进程是否存活 | 公开 |
| GET /health/ready | 数据库能否连通、结构是否已迁移到当前版本 | 公开 |
| GET /api/system/modules | 模块目录和模块关系图 | system.diagnostics |
| GET /api/system/flows/{操作名} | 操作的步骤、字段含义、调用关系、计算流程图和全部字段的来源 | system.diagnostics |
| GET /api/system/fields/{操作名}/{字段} | 逐层说明一个字段怎样得出 | system.diagnostics |
| GET /api/system/runs | 最近的运行和中文摘要，可按模块、状态、请求编号、任务编号筛选 | system.diagnostics |
| GET /api/system/runs/{运行编号} | 一次运行的全部记录（含下一层调用）和实际执行图 | system.diagnostics |
| GET /api/system/runs/{运行编号}/report | 中文运行报告（Markdown） | system.diagnostics |
| GET /api/system/runtime | 内存、在途请求、连接池、运行记录缓冲、任务数量 | system.diagnostics |
| GET /api/jobs/{任务编号} | 查看自己登记的任务 | 登记者本人或 system.jobs |
| GET /api/system/jobs | 列出任务 | system.jobs |

这些接口只读。重新排队、取消任务等修改操作只能通过命令行 `tools.jobs` 进行，并要求 `--yes` 确认。

开启 `APP_CONSOLE=true` 后，访问 `/system/console` 查看模块关系、步骤、最近运行、运行统计、进程状态和操作记录。页面由本目录的 `console.html` 与 `console.js` 提供，不加载外部脚本。输入有相应权限的服务密钥或用户令牌；凭据只留在当前页面。

运行详情显示上下层调用、失败位置、每步耗时和本次用时最长的步骤。启用自动刷新后约每三秒更新；后台进程会把执行中的记录写入共用数据库，因此接口进程也能显示进度。生成的 Mermaid 图代码与原始数据可展开查看。
