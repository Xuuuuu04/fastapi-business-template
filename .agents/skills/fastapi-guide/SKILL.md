---
name: fastapi-guide
description: 采用或阅读本 FastAPI 模板、准备启动与规划开发时使用。业务迁移另读 fastapi-migration；具体实现按有关 Skill 执行。
---

# 模板使用

本模板是无预置业务的 FastAPI 单体：业务包固定在 `server/service/`，公共能力在 `server/shared/`，HTTP 与启动在 `server/app/`。步骤声明字段读写，计算在步骤，SQL 在存储，跨包只调用声明的公开操作。

从项目根目录查看 `AGENTS.md`、`project-plan.json` 与 `doc/README.md`，只展开当前业务有关资料。先做一项可检查、可使用的业务结果；依赖顺序用于当前业务内部安排，不要求全项目自下而上逐层完成。

在 `server/` 启动：

```bash
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

第一次使用要填写 `.env`；已有配置不覆盖。新模板的初始迁移只适用于新数据库，既有产品保留自己的迁移历史。部署、真实外部写入与删除真实数据按用户授权范围执行。

按任务读取同目录下的 Skill：

- `fastapi-template`：新产品副本、框架更新。
- `fastapi-module`：新业务包与结构调整。
- `fastapi-project`：计划、当前检查、运行和影响范围。
- `fastapi-docs`：生成代码声明对应的文档。
- `fastapi-check`：局部、共同版本及完整检查。
- `fastapi-operations`：运行查询、后台任务与服务密钥。
- `fastapi-migration`：逐项替换旧业务、复用旧计算。

这些 Skill 随项目复制；只复制 `.agents/skills/`，不复制本机任务、证据或工作目录。生产服务不导入 Skill 脚本。
