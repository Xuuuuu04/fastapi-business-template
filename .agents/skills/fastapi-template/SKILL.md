---
name: fastapi-template
description: 从本模板创建新产品，或把模板的框架更新合并进已有产品时使用。更新脚本不会处理业务代码和数据库迁移。
---

# 模板管理

新建产品和更新旧产品是两件事。命令在 `server/` 执行，脚本按自己所在位置找到项目。

```bash
# 创建新产品
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py start_project /新项目目录 --name 产品名称
# 更新已有产品的框架（默认只预览）
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /旧模板 --source /新模板 --target /产品目录
```

## 创建新产品

- 目标目录必须不存在，并且不能在模板目录里面。
- 脚本会重新创建产品入口文档、计划和任务，复制公共代码和项目 Skill。不复制环境配置、虚拟环境、运行数据、本机记录和 Git 历史。
- 脚本不创建数据库。创建后在新产品里重新安装依赖，再生成需要的业务包。

## 更新已有产品

先读 [更新说明](references/upgrading.md)，再运行预览，看清实际会改哪些文件。

- 比较三份内容：旧模板、当前产品、新模板。只要有一处冲突，就不写入任何文件。
- 依赖、配置、业务登记、业务代码、迁移历史由产品自己维护，脚本不碰。
- 预览确认没问题，并且在授权范围内，再加 `--apply` 执行。

更新之后：检查改动的共同影响，生成文档，用 `fastapi-check` 更新框架摘要并运行相应检查。

## 恢复

还没部署的更新，用 Git 撤回。数据库和部署出了问题，需要产品自己准备的备份和恢复方案，脚本不提供。
