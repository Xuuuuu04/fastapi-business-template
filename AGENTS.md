# FastAPI 单体后端模板 4.1.0

## 业务要点

产品在这里写三五条每次改代码都要知道的业务事实：做什么、谁用、最要紧的规则。完整的业务说明在[业务文档](.agents/skills/fastapi-business/business.md)。

## 目录

| 位置 | 放什么 |
| --- | --- |
| `server/service/` | 业务包 |
| `server/library/` | 纯工具包 |
| `server/shared/` | 框架 |
| `server/app/` | HTTP 和启动；业务包登记在 `app/setup/catalog.py` 的 `MODULES`，路由登记在 `app/api/routers.py` 的 `MODULE_ROUTERS`，生成命令会自动写 |
| `server/app/product.py` | 产品组装：名称、供应商、时钟等 |
| `doc/api/openapi.json` | 唯一生成的文档，给前端用 |

## 怎么运行

在 `server/` 执行，已有 `.env` 不覆盖：

```bash
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

## 按任务找 Skill

| 要做的事 | Skill |
| --- | --- |
| 了解业务、找代码、业务做完更新业务文档 | [fastapi-business](.agents/skills/fastapi-business/SKILL.md) |
| 写或改业务代码 | [fastapi-module](.agents/skills/fastapi-module/SKILL.md) |
| 检查和测试 | [fastapi-check](.agents/skills/fastapi-check/SKILL.md) |
| 发布上线、查运行、处理后台任务 | [fastapi-operations](.agents/skills/fastapi-operations/SKILL.md) |
| 新建产品、升级框架、迁移旧系统 | [fastapi-template](.agents/skills/fastapi-template/SKILL.md) |

开发命令都是 `uv run dev 子命令`，在 `server/` 执行。

## 日常流程

1. 改代码，调试时跑 `uv run dev check --quick --module 包`。
2. 用 `uv run dev run 操作名 --input '{...}' --allow-write` 真跑一次，看运行报告对不对。
3. 提交前跑 `uv run dev check --module 包`；改了框架或公共代码跑 `uv run dev check`。
4. 提交，在 `main` 上执行 `uv run dev deploy` 推送并上线。
5. 一项业务做完，按 fastapi-business 更新业务文档。

## 长期约定

- 框架文件（清单在 `server/shared/modules/validation/framework_files.py`）做业务时不改；确要改，在提交说明里写用途和影响。业务文档不算框架文件。
- 凭据或权限不够时停下说明，不去找别的凭据。
- 探索、生成、验证和诊断走项目 Skill 的标准命令；复用业务样例用 `dev run --case`，工具扩展约定见 fastapi-check。
