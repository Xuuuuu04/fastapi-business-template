---
name: fastapi-template
description: 用模板新建产品、把新版模板的框架更新合进已有产品、或把旧系统的一项业务迁进来时读。日常写业务看 fastapi-module。
---

# 新建产品、升级框架、迁移旧业务

命令在 `server/` 执行。

| 命令 | 做什么 |
| --- | --- |
| `uv run dev new-project /新项目目录 --name 产品名称` | 从模板创建新产品 |
| `uv run dev upgrade --base /旧模板 --source /新模板 --target /产品目录` | 预览框架更新，加 `--apply` 写入 |
| `uv run dev compare-api --before 旧openapi.json --after ../doc/api/openapi.json` | 比较两份接口文档的差异 |

## 新建产品

- 目标目录必须还不存在，而且不在模板目录里面。
- 复制框架代码、项目 Skill 和配置示例，重写 `AGENTS.md`、`README.md`、`CHANGELOG.md` 和 `app/product.py`。不复制 `.env`、虚拟环境、运行数据和 Git 历史，也不建数据库。
- 建好后在新目录里 `git init`、`uv sync`、填 `.env`、`uv run alembic upgrade head`，在 `AGENTS.md` 的“业务要点”写上产品做什么、谁用，再按 fastapi-module 生成业务包。

## 升级框架

按[升级说明](references/upgrading.md)做：准备旧模板和新模板两份目录，先预览，没有冲突再加 `--apply`，之后跑 `uv run dev docs` 和 `uv run dev check`。

- 脚本比较旧模板、产品、新模板三份文件，有一个冲突就一个文件都不写。
- 依赖、配置、业务登记、业务代码、迁移历史和业务文档由产品自己维护，脚本不碰。

## 迁移旧业务

一次迁一项用户能用的完整业务，按[迁移说明](references/product-migration.md)做。
