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

没有配置大模型时，订单报价的说明使用模拟回复（“本地模拟回复，没有调用真实模型”）。配置方法见 `.env.example` 中的 `APP_MODEL_*`。

## 2. 目录

| 目录 | 内容 |
| --- | --- |
| [app](app/) | HTTP 接口、启动组装、模块总目录 |
| [service](service/) | 业务模块，每个模块结构相同 |
| [shared](shared/) | 框架：业务代码只从 `shared.public` 导入 |
| [tools](tools/) | 开发命令：新建模块、全量检查、导出文档、诊断、任务处理 |
| [tests](tests/) | 测试，按用途分目录 |
| [migrations](migrations/) | 数据库结构迁移 |
| [deploy](deploy/) | Docker、组合配置、环境检查、备份恢复 |

建议阅读顺序：`service/README.md` → 一个示例模块（先看 `order_quote/README.md`，再看 `flow.py` 和 `steps/`）→ `shared/flow/README.md`。

## 3. 常用命令

| 做什么 | 命令 |
| --- | --- |
| 全量检查（提交前必须通过） | `uv run python -m tools.check` |
| 在 PostgreSQL 上再跑测试 | `uv run python -m tools.check --postgres postgresql+psycopg://用户:密码@主机:端口/库` |
| 新建业务模块 | `uv run python -m tools.new_module 模块名 --title 中文名` |
| 删除两个示例模块（新项目开始时） | `uv run python -m tools.remove_examples --yes` |
| 生成迁移 | `uv run alembic revision --autogenerate -m "说明"` |
| 生成文档 | `uv run python -m tools.export_docs` |
| 查看运行记录 | `uv run python -m tools.diagnose runs --status failed` |
| 查看一次运行的报告 | `uv run python -m tools.diagnose run 运行编号` |
| 查看操作的流程和字段来源 | `uv run python -m tools.diagnose flow order_quote.create_quote` |
| 生成服务密钥 | `uv run python -m tools.make_key --name 名称 --permissions 权限` |

## 4. 出问题时怎样查

1. 错误响应和响应头里有运行编号 `run_id`（响应头 `X-Run-ID`）。
2. 调用 `GET /api/system/runs/{run_id}/report`（需要 `system.diagnostics` 权限）或运行 `tools.diagnose run`，得到中文报告：停在哪一步、错误说明、出错的源码位置、每一步写入了什么、调用了哪些下一层操作、大模型用了哪个提示词版本。
3. 按报告中的规则编号读 `doc/模块名/rules.md`，确认预期结果。
4. 最后读出错位置附近的源码和对应测试。

## 5. 验证情况

默认测试覆盖框架、业务规则、HTTP 接口、约定、架构、质量、安全和恢复，在 SQLite 和 PostgreSQL 17 上都已运行。压力测试（`tests/load`）和浏览器检查（`tests/browser`）需要手动运行。
