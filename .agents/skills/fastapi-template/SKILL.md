---
name: fastapi-template
description: 创建新产品、接收模板框架升级或逐项迁移旧业务时使用。框架更新与业务迁移按各自参考执行。
---

# 模板管理

新建产品和更新旧产品是两件不同的事。命令在 `server/` 目录执行，脚本按自己所在的位置找到项目。

```bash
# 创建新产品
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py start_project /新项目目录 --name 产品名称
# 更新已有产品的框架（默认只预览）
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /旧模板 --source /新模板 --target /产品目录
```

## 创建新产品

- 目标目录必须不存在，而且不能放在模板目录里面。
- 脚本会重新创建产品的入口文档、计划和任务，复制公共代码和项目 Skill。环境配置、虚拟环境、运行数据、本机记录和 Git 历史都不会复制。
- 脚本不创建数据库。创建之后，在新产品里重新安装依赖，再生成需要的业务包。

## 更新已有产品

先读[更新说明](references/upgrading.md)，再运行预览，看清实际会改哪些文件。

- 脚本比较三份内容：旧模板、当前产品、新模板。只要有一处冲突，就不写入任何文件。
- 依赖、配置、业务登记、业务代码、迁移历史由产品自己维护，脚本不会碰。
- 预览确认没有问题、并且改动在授权范围内，再加 `--apply` 执行。

更新之后：检查改动的共同影响，生成文档，用 `fastapi-check` 更新框架摘要并运行相应的检查。

## 迁移旧业务

把旧系统的一项完整业务迁入时，读[业务迁移](references/product-migration.md)；需要记录当前实现、旧页面和正式切换状态时，读[迁移记录示例](references/product-migration-report.md)。框架更新脚本保护业务目录和迁移历史，不能用框架文件更新代表业务已迁移。

可以显式传 `--recovery-proof /产品升级任务/recovery-proof.json` 接收本产品已审查的补丁；模板不附带产品证明，格式与限制见[回收说明](references/framework-recovery.md)。

## 恢复

还没有部署的更新，用 Git 撤回。数据库和部署出了问题，需要产品自己准备的备份和恢复方案，脚本不提供。
