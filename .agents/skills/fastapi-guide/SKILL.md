---
name: fastapi-guide
description: 第一次接触本 FastAPI 模板、要启动项目或规划开发顺序时使用。迁移旧系统另读 fastapi-migration，具体实现读下面列出的对应 Skill。
---

# 模板入门

## 项目结构

这是一个没有预置业务的 FastAPI 单体后端：

- `server/service/`：业务包，每个业务一个包，目录结构固定。
- `server/shared/`：所有业务共用的能力，如事务、流程执行、后台任务。
- `server/app/`：HTTP 接口和启动。

业务代码的分工：步骤（`steps/`）声明自己读写哪些字段并做计算；SQL 只写在存储（`store/`）里；一个包要用另一个包，只能调用对方公开的操作。

## 开始之前

1. 在项目根目录读 `AGENTS.md`、`project-plan.json` 和 `doc/README.md`，只展开当前要做的业务相关的文档。
2. 先做出一项能检查、能使用的业务。一项业务内部按依赖先后安排即可，不需要整个项目先把底层全做完再往上做。

## 启动

在 `server/` 执行：

```bash
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

- 第一次使用需要填写 `.env`，已有的 `.env` 不要覆盖。
- 模板自带的初始迁移只用于全新数据库。已经上线的产品保留自己的迁移历史。
- 部署、写入真实外部系统、删除真实数据，只在用户明确授权的范围内做。

## 按任务选 Skill

| 要做的事 | 读哪个 |
|---|---|
| 创建新产品、更新框架 | `fastapi-template` |
| 新建业务包、调整包结构 | `fastapi-module` |
| 查看计划、检查记录、运行记录、改动影响 | `fastapi-project` |
| 生成接口、字段、流程文档 | `fastapi-docs` |
| 运行局部检查、联合检查、完整检查 | `fastapi-check` |
| 查运行报告、处理后台任务、生成服务密钥 | `fastapi-operations` |
| 把旧系统业务逐项迁进来 | `fastapi-migration` |
| 给 Vue3 前端提供接口、前后端字段对不上、前端出错查后端 | `fastapi-frontend` |

## 复制项目时

只复制 `.agents/skills/`。本机的任务记录、检查证据和临时工作目录不要带走。生产服务不会导入 Skill 里的脚本。
