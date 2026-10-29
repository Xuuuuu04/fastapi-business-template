# FastAPI 单体后端模板 3.2.0

空业务模板（`MODULES=[]`），产品在 `server/app/product.py` 组装。业务包在 `server/service/`，纯工具在 `server/library/`，框架在 `server/shared/`，HTTP 和启动在 `server/app/`。

## 业务要点

产品在这里写三五条每次改代码都要知道的业务事实：做什么、谁用、最要紧的规则。完整的业务说明在[业务文档](.agents/skills/fastapi-business/business.md)。

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

改代码，跑 `uv run dev check --quick --module 包`，过了就提交并推主干，上线用 `uv run dev deploy`。一项业务做完，按 fastapi-business 更新业务文档。

## 长期约定

- 框架文件（清单在 `server/shared/modules/validation/framework_files.py`）做业务时不改；确要改，在提交说明里写用途和影响。
- 凭据或权限不够时停下说明，不去找别的凭据。
