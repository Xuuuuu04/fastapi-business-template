---
name: fastapi-template
description: 基于模板初始化新产品、把新版框架升级到已有产品、或迁移旧系统业务到本模板时读。日常写业务、跑检查或发布时不用读。
---

# 新建产品、升级框架、迁移旧业务

沿着统一模板与升级流程落地新产品或同步框架版本，保护产品业务不被模板覆盖。

## 执行步骤

1. **从模板创建新产品**。在模板仓库的 `server/` 下执行 `uv run dev new-project /新项目目录 --name 产品名称`，注意新目录必须尚未存在且位于模板仓库之外：
   - `new-project` 会复制框架代码、Skill 和配置示例，重写 `AGENTS.md`、`README.md`、`CHANGELOG.md`、`app/product.py`，更新 `server/pyproject.toml`、`server/uv.lock`、`server/.env.example`，并写入来源记录 `template-source.json`。
   - 初始化完成后进入新产品目录依次执行 `git init`、`uv sync`、填写 `.env` 和 `uv run alembic upgrade head`，再把产品规则写进 `AGENTS.md` 的“业务要点”，按 `fastapi-module` 开发业务。
2. **把新版模板框架合并到已有产品**。在新版本模板的 `server/` 下对照新旧模板提交运行预览和升级（详查[升级说明](references/upgrading.md)）：

   ```bash
   uv run dev upgrade --base /旧模板 --source /新模板 --target /产品目录
   uv run dev upgrade --base /旧模板 --source /新模板 --target /产品目录 --apply
   ```

   遇到冲突时停止并先按业务规则解决冲突；合入后手工检查 `manual_review` 清单里的依赖、`uv.lock` 与迁移，再跑完 `uv run dev docs` 与 `uv run dev check`。
3. **逐项迁移并比对旧系统业务**。每次只迁一项可完整走通的业务，按[迁移说明](references/product-migration.md)将纯计算与存储拆分后接上接口，最后在产品 `server/` 用接口对比命令核对兼容变化：

   ```bash
   uv run dev compare-api --before 旧openapi.json --after ../doc/api/openapi.json
   ```

## 验收

新产品已脱离模板 Git 历史且基线 `uv run dev check` 通过；框架升级或旧业务迁入后，`dev docs` 与完整 `dev check` 全部通过，没有遗漏依赖或破坏既有接口契约。
