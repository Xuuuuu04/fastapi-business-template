# 后端服务

FastAPI 单体后端。每个业务模块按固定结构组织，每个接口背后是一个登记过的操作，每次执行都留下可以按运行编号查询的记录和中文摘要。

## 1. 本地运行

在 `server/` 目录执行：

```bash
uv sync
cp .env.example .env                 # 本地默认 SQLite，开发者身份已开启
uv run alembic upgrade head          # 建表（第一次和每次拉取新迁移后）
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

打开 http://127.0.0.1:8000/docs 调用接口。后台任务需要另开一个终端运行 worker：

```bash
uv run python -m app.setup.worker
```

模板没有默认的大模型业务。只有模块声明提示词时才创建大模型服务；启用方式见 `.env.example` 中的 `APP_MODEL_*`。
模块与运行页面位于 `/system/console`；可查看模块关系、执行步骤、失败位置和耗时，生产环境默认关闭。选择自动刷新后每三秒读取当前内容。

## 2. 目录

| 目录 | 内容 |
| --- | --- |
| [app](app/) | HTTP 接口、启动组装、模块总目录 |
| [service](service/) | 业务模块，每个模块结构相同 |
| [shared](shared/) | 框架：业务代码只从 `shared.public` 导入 |
| [tools](tools/) | 开发命令：新建模块、全量检查、导出文档、排查、任务处理 |
| [tests](tests/) | 测试，按用途分目录 |
| [migrations](migrations/) | 数据库结构迁移 |
| [legacy](legacy/) | 旧系统表的独立定义和迁移说明 |
| [deploy](deploy/) | Docker、组合配置、环境检查、备份恢复 |

建议阅读顺序：`service/README.md` → `shared/flow/README.md` → `tools/new_module.py`。模板没有预置业务模块；下方客户、订单模块命令是写法示例，先生成对应模块再执行。

## 3. 常用命令

| 做什么 | 命令 |
| --- | --- |
| 完整检查（整批交付和发布前） | `uv run python -m tools.check` |
| 在 PostgreSQL 上再跑测试 | `uv run python -m tools.check --postgres postgresql+psycopg://用户:密码@主机:端口/库` |
| 新建业务模块 | `uv run python -m tools.new_module 模块名 --title 中文名` |
| 单独检查一个模块 | `uv run python -m tools.check --module customer_contact` |
| 子代理快速调试（不代替验收） | `uv run python -m tools.check --quick --module customer_contact` |
| 一次验收整层多个模块 | `uv run python -m tools.check --module customer_contact --module order_records` |
| 根据新旧依赖检查受影响包 | `uv run python -m tools.check --affected --base origin/main` |
| 生成迁移 | 先 `uv run alembic upgrade head`，再 `uv run alembic revision --autogenerate -m "说明"` |
| 生成文档 | `uv run python -m tools.export_docs` |
| 查看运行记录 | `uv run python -m tools.diagnose runs --status failed` |
| 查看一次运行的报告 | `uv run python -m tools.diagnose run 运行编号` |
| 查看运行统计 | `uv run python -m tools.diagnose stats --hours 24` |
| 查看操作的流程和字段来源 | `uv run python -m tools.diagnose flow customer_contact.get_record` |
| 生成服务密钥 | `uv run python -m tools.make_key --name 名称 --org-id 组织 --permissions 权限` |

快速检查只做所选包的风格、格式和业务测试。正式单包或多包检查还做完整风格、增量类型、生成文档，以及一次导入、登记和迁移一致性检查，不重跑全部框架测试。`--affected` 对公共或未知变化保守执行完整检查；没有改动时报告未执行。每轮保存各项耗时，测试另列最慢的准备、执行与清理阶段；旧记录没有耗时则保持未知。并行测试必须使用独立数据库。

批量迁移前主代理先读 [分层开发指南](../doc/agent-development.md)。

## 4. 出问题时怎样查

1. 错误响应和响应头里有运行编号 `run_id`（响应头 `X-Run-ID`）。
2. 调用 `GET /api/system/runs/{run_id}/report`（需要 `system.diagnostics` 权限）或运行 `tools.diagnose run`，得到中文报告：停在哪一步、错误说明、出错的源码位置、每一步写入了什么、调用了哪些下一层操作、大模型用了哪个提示词版本。
3. 按报告中的规则编号读 `doc/模块名/rules.md`，确认预期结果。
4. 最后读出错位置附近的源码和对应测试。

## 5. 常用能力

| 能力 | 模块或入口 | 配置与使用 |
| --- | --- | --- |
| 外部接口 | `shared/remote_calls` | 模块声明 `remote(...)`，配置 `APP_REMOTES`，步骤通过 `remote` 参数调用 |
| 旧系统迁移 | `legacy/`、存储构造参数 `legacy` | 配置 `APP_LEGACY_DATABASE_URL`；旧库只读，旧表不进入本系统迁移 |
| 缓存 | `shared/cache` | 步骤或存储使用 `cache`；多实例设置 `APP_CACHE_URL` 指向 Redis |
| 流式输出 | `/api/v1/stream/{操作名}` | 操作声明 `stream=True`，异步步骤通过 `emit` 输出 SSE 分段 |
| 统计和操作记录 | `/api/system/stats`、`/api/system/audit` | 需 `system.diagnostics`、`system.audit` 权限 |
| 运行追踪 | `shared/telemetry` | 配置 `APP_OTEL_ENDPOINT` 导出 OTLP HTTP traces |

安全响应头与按调用者限流默认启用。组织隔离表使用 `org_column()`，业务数据库入口检查组织条件；公共能力保留服务密钥、Bearer 令牌校验与敏感字段加密。用户登录、角色管理和文件业务接口由产品自行实现。

## 6. 验证情况

检查结果以当前提交的 `tools.check` 输出和持续集成结果为准，不在这里保存会过期的数量。发布前按目标环境验证 PostgreSQL、文件存储、缓存、备份恢复与压力；本机测试不能代表客户环境容量。

关闭模块使用 `APP_DISABLED_MODULES`；例如关闭文件模块时设置 `["customer_contact"]`。模块接口和后台计划一起关闭，已有表和数据不删除。启用状态有依赖冲突时服务拒绝启动。复制项目不要复制 `.venv`，在目标目录重新执行 `uv sync --locked`，避免命令仍指向原项目。
