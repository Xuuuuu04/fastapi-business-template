---
name: fastapi-template
description: 用模板新建产品、把新版模板的框架代码更新到已有产品、或把旧系统的一项业务迁到本模板时读。日常写业务、检查、发布时不用读。
---

# 新建产品、升级框架、迁移旧业务

| 命令 | 在哪执行 | 做什么 |
| --- | --- | --- |
| `uv run dev new-project /新项目目录 --name 产品名称` | 模板仓库的 `server/` | 从模板创建新产品；在产品里执行会把产品的业务代码一起复制走 |
| `uv run dev upgrade --base /旧模板 --source /新模板 --target /产品目录` | 新模板的 `server/` | 预览框架更新，加 `--apply` 写入 |
| `uv run dev compare-api --before 旧openapi.json --after ../doc/api/openapi.json` | 产品的 `server/` | 比较两份接口文档的差异 |

## 新建产品

- 目标目录必须还不存在，而且不在模板目录里面。
- 复制框架代码、项目 Skill 和配置示例，重写 `AGENTS.md`、`README.md`、`CHANGELOG.md` 和 `app/product.py`。不复制 `.env`、虚拟环境、运行数据和 Git 历史，也不建数据库。
- 建好后在新目录里 `git init`、`uv sync`、填 `.env`、`uv run alembic upgrade head`，在 `AGENTS.md` 的“业务要点”写上产品做什么、谁用，再按 fastapi-module 生成业务包。

## 升级框架

按[升级说明](references/upgrading.md)做：准备旧模板和新模板两份目录，先预览改动，没有冲突再加 `--apply`，之后跑 `uv run dev docs` 和 `uv run dev check`。

## 迁移旧业务

一次迁一项用户能用的完整业务，按[迁移说明](references/product-migration.md)做。
