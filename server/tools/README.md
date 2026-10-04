# tools：开发命令

| 命令 | 用途 |
| --- | --- |
| `uv run python -m tools.check` | 全量检查：代码风格、格式、类型、生成文档、默认测试；加 `--module 模块名` 只跑该模块的步骤和接口测试，其他代码检查保留；加 `--postgres 地址` 在 PostgreSQL 上再跑测试 |
| `uv run python -m tools.project [--json] [--module 模块名] [--runs]` | 项目根、业务线、开发包、缺少的操作、真实测试轮次、计算图与源码；运行记录按需查询 |
| `uv run python -m tools.start_project /新项目目录 --name 产品名称` | 生成产品原生的干净副本，保留框架来源，重新开始业务计划与任务 |
| `uv run python -m tools.update_framework --base /旧模板 --source /新模板 [--apply]` | 三份文件比较，只接收框架变化；默认预览，冲突时全部保留；旧产品可加 `--target /产品目录` |
| `uv run python -m tools.new_module 模块名 --title 中文名` | 生成新业务模块的完整骨架并登记 |
| `uv run python -m tools.adopt_modules` | 旧项目的全部业务包检查通过后写入标准结构说明，不改业务代码 |
| `uv run python -m tools.export_docs` | 生成 doc/ 下的文档：接口描述（doc/api）、模块关系、各模块流程、开发进度（doc/progress.md）；`--check` 只检查是否过期 |
| `uv run python -m tools.diagnose runs/run/flow/field/stats` | 查看运行记录、排查报告、流程、字段来源和统计 |
| `uv run python -m tools.jobs list/show/requeue/cancel` | 查看和人工处理后台任务 |
| `uv run python -m tools.make_key --name 名称 --org-id 组织 --permissions 权限` | 生成带组织范围的服务密钥 |
| `uv run python -m tools.impact --base origin/main` | 改动影响报告：框架文件、涉及的模块、规则增删改、待确认数量、操作流程、接口、迁移；持续集成写到合并请求的检查摘要页 |
| `uv run python -m tools.compare_api --before 旧 --after 新` | 比较两份接口文档（`tools.impact` 已自动与基准分支比较） |
| `uv run python -m tools.framework_lock` | 检查框架文件是否被改动；审查后用 `--update` 更新。`pyproject.toml` 只锁定 `[tool]` 下的检查配置，改依赖版本不需要更新 |

- [quality](quality/)：质量检查规则，默认测试会调用。
- [templates](templates/)：新模块的模板。
- [development](development/)：项目设计、检查历史与开发视图。
- [template](template/)：初始化、来源与更新规则；[已有产品升级](template/UPGRADING.md)。

检查轮次只统计本机留存记录；失败、跳过、数据库类型和源码摘要分别保存。
`doc/development.md` 只保存计划与代码结构，实际测试结果放在忽略提交的 `var/development/checks/`。
