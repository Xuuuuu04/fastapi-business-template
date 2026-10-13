---
name: fastapi-guide
description: 第一次接触本 FastAPI 模板、启动项目或规划开发顺序时使用。具体开发与迁移按六类入口展开。
---

# 模板入门

找不到该改哪里时，先在 `server/` 下执行 `uv run dev locate --query "业务词或旧接口路径" --limit 10 --json`，再按结果执行 `uv run dev status --operation 模块.操作 --json`。定位只读本地声明和规则文档，不访问数据库；旧路径如果没有保留下来，它们的关系就是未知的。

## 项目结构

这是一个没有预置业务的 FastAPI 单体后端，按职责分开：

- `server/service/`：业务包，每个业务一个包，目录结构固定。
- `server/library/`：纯工具包，不访问数据库、网络或业务运行状态。
- `server/shared/`：所有业务共用的框架能力，比如事务、流程执行、后台任务。
- `server/app/`：HTTP 接口和启动。

`service/` 内，能力包负责存取与公开操作，流程包负责组合业务链；工具包放 `library/`，只做纯计算，不反向依赖业务包。

业务代码的分工：步骤（`steps/`）声明自己读写哪些字段并做计算；SQL 只写在存储（`store/`）里；一个包要用另一个包的能力，只能调用对方公开的操作。

## 开始之前

1. 在项目根目录读 `AGENTS.md`、`project-plan.json` 和 `doc/README.md`，只展开和当前业务相关的文档。
2. 先做出一项能检查、能使用的完整业务。一项业务内部按依赖先后安排就够了，不需要整个项目先把底层全做完再往上做。

## 日常开发

在 `server/` 下，先 `uv run dev start --package 包 --cases 样例` 确认任务与独立样例，实现后 `uv run dev check --module 包` 检查，最后 `uv run dev finish --task 编号` 留下完成证据。交付用 `uv run dev check --delivery` 强制重新执行，数据库选择见 check Skill。

## 启动

在 `server/` 目录执行：

```bash
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

- 第一次使用需要填写 `.env`；已经存在的 `.env` 不要覆盖。
- 模板自带的初始迁移只用于全新的数据库。已经上线的产品保留自己的迁移历史。
- 部署、写入真实外部系统、删除真实数据，只在用户明确授权的范围内做。

## 按任务选 Skill

| 要做的事 | 读哪个 |
|---|---|
| 创建新产品、更新框架 | `fastapi-template` |
| 新建业务包、操作、流程、纯工具与前后端接口 | `fastapi-module` |
| 计划、规则、任务、文档、面板、整合与证据 | `fastapi-project` |
| 运行局部检查、联合检查、完整检查 | `fastapi-check` |
| 查运行报告、处理后台任务、生成服务密钥 | `fastapi-operations` |

业务迁移见 `fastapi-template` 的迁移参考，前后端接口适配见 `fastapi-module` 的接口参考。六个日常 Skill 入口包含本 guide；`fastapi-docs`、`fastapi-migration` 目录仅保留兼容 Python 工具，不是额外的 Skill 入口。旧长命令保持兼容；日常优先用 `uv run dev`。

写文档和生成文字时，遵循 [文风与术语约定](references/writing-style.md)：完整句子、统一术语、图上只放流程、细节进表格。

## 复制项目时

只复制 `.agents/skills/`。本机的任务记录、检查证据和临时工作目录不要带走。生产服务不会导入 Skill 里的脚本。
