# tools：开发命令

| 命令 | 用途 |
| --- | --- |
| `uv run python -m tools.check` | 全量检查：代码风格、格式、类型、生成文档、默认测试；加 `--postgres 地址` 在 PostgreSQL 上再跑测试 |
| `uv run python -m tools.new_module 模块名 --title 中文名` | 生成新业务模块的完整骨架并登记 |
| `uv run python -m tools.export_docs` | 生成 doc/ 下的流程文档和 out/api 下的接口文档；`--check` 只检查是否过期 |
| `uv run python -m tools.diagnose runs/run/flow/field/stats` | 查看运行记录、诊断报告、流程、字段来源和统计 |
| `uv run python -m tools.jobs list/show/requeue/cancel` | 查看和人工处理后台任务 |
| `uv run python -m tools.make_key --name 名称 --org-id 组织 --permissions 权限` | 生成带组织范围的服务密钥 |
| `uv run python -m tools.compare_api --before 旧 --after 新` | 比较两份接口文档 |
| `uv run python -m tools.framework_lock` | 检查框架文件是否被改动；审查后用 `--update` 更新 |

- [quality](quality/)：质量检查规则，默认测试会调用。
- [templates](templates/)：新模块的模板。
