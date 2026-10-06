---
name: fastapi-template
description: 从本模板创建干净新产品、比较并更新已有产品公共框架时使用；业务和数据库迁移不由更新脚本自动执行。
---

# 模板管理

新产品与旧产品更新分开处理。以下命令在 `server/` 执行，脚本从自己的路径确定项目。

```bash
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py start_project /新项目目录 --name 产品名称
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /旧模板 --source /新模板 --target /产品目录
```

新产品目标必须不存在且位于模板之外。脚本重新创建产品入口、计划与任务，复制公共代码和项目 Skill，排除环境、虚拟环境、运行数据、本机记录和 Git 历史。随后在新产品重新安装依赖、生成所需业务模块；脚本不创建数据库。

更新前读 [更新说明](references/upgrading.md)，先看脚本预览与实际差异。三份比较分别为旧模板、当前产品、新模板；冲突时不写入任何更新。依赖、配置、业务登记、业务代码与产品迁移历史由产品维护。确认方案在已授权范围内后加 `--apply`。

更新后检查共同影响，生成文档，再用项目检查 Skill 更新框架摘要并运行适用检查。未部署的变更由 Git 恢复；数据库与部署需要产品自己的恢复方案。
