# FastAPI 单体后端模板 3.2.0

这是空业务模板，`MODULES=[]`；产品通过自己的 `app/product.py` 组装。业务实现放 `server/service/`，纯工具放 `server/library/`，共享框架放 `server/shared/`，HTTP 与启动放 `server/app/`。

## 怎么运行

在 `server/` 执行：

```bash
uv sync --locked
uv run dev inspect
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

首次启动按 `.env.example` 填配置；已有 `.env` 不覆盖。新库执行 `uv run alembic upgrade head`；旧库保留迁移历史，先读升级说明。

## 按任务找入口

| 任务 | Skill |
| --- | --- |
| 入门、开发约定、运行 | [guide](.agents/skills/fastapi-guide/SKILL.md) |
| 包、工具、操作、流程、前后端接口 | [module](.agents/skills/fastapi-module/SKILL.md) |
| 静态检查与测试 | [check](.agents/skills/fastapi-check/SKILL.md) |
| 运行报告、任务恢复、回放和部署 | [operations](.agents/skills/fastapi-operations/SKILL.md) |
| 新项目、框架升级、旧业务迁移 | [template](.agents/skills/fastapi-template/SKILL.md) |

以上是五个日常 Skill 入口。`fastapi-project`、`fastapi-docs`、`fastapi-migration` 只放 `dev locate`、`dev docs`、`dev compare-api` 的脚本，没有独立 SKILL.md。找代码用 `uv run dev locate --query 业务词`。

日常执行 `uv run dev check --module 包`，交付前跑 `uv run dev check --delivery`。

## 长期约定

- 业务规则先问清并写成测试样例，再实现。默认一个代理负责到底。
- 能力包负责存取，流程包负责业务链，工具包只做纯计算；包间调用公开操作，SQL 只放存储，步骤声明读写字段。
- 公共框架和开发工具由 `server/framework.lock` 保护；确需修改时说明用途、影响和验证，审查后更新摘要，不降低检查阈值。
- 项目不生成文档，唯一的生成物是 `doc/api/openapi.json`，供前端和 compare-api 使用。检查和业务验收分开。
- 凭据或权限不够时停下说明，不搜索其他凭据。生产写入、外部动作和切换按实际授权处理。
- 测试失败的运行报告在 `server/var/development/failures/`，不提交、不复制进新产品。
