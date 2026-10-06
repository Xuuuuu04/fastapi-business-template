# 已有产品接收框架更新

本工具处理已复制模板或通过 GitHub 模板创建、没有共同 Git 祖先的项目。
不要求把模板的全部提交合入产品。它只比较框架文件，业务模块、注册清单、业务文档、
项目计划、环境、依赖版本和数据库迁移历史由产品保留。

## 准备旧模板和新模板

先在产品中保存当前工作，使用独立分支。新项目的 `template-source.json` 记录上次采用的
模板版本、Git 提交和文件摘要。未使用初始化工具的旧项目，需要从其第一次复制模板的
提交或版本取出旧模板；不能拿一个猜测版本当作旧模板，否则无法可靠识别自己的修改。

```bash
git clone https://github.com/Xuuuuu04/fastapi-business-template.git /tmp/template-upgrade
git -C /tmp/template-upgrade worktree add --detach /tmp/template-old 旧模板提交或标签
git -C /tmp/template-upgrade worktree add --detach /tmp/template-new 新模板提交或标签
```

如果旧产品还没有这些工具，在新模板的 `server/` 下运行，并明确指定产品目录：

```bash
uv sync
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --target /产品目录 \
  --base /tmp/template-old --source /tmp/template-new
```

审查后在同一命令末尾加 `--apply`。未加时不写入产品。

## 预览和接收

已有工具的产品在自己的 `server/` 下运行：

```bash
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /tmp/template-old --source /tmp/template-new
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /tmp/template-old --source /tmp/template-new --apply
```

比较规则：产品没有改过的文件接收新版；两边改不同位置时尝试文本合并；同一处改动、
新增文件重名、上游删除了产品修改过的文件、产品删除了上游修改过的文件都显示冲突。
有任何冲突时所有文件保持原样。默认只预览；`--apply` 保存前再次检查，保存失败会恢复本次写入。
文件链接或越出项目的路径被拒绝。工具从未访问或修改数据库。

人工解决冲突时，以规则和接口含义决定最终结果；之后重跑预览。接受完新版后，
`template-source.json` 记录新模板文件摘要。产品自身的修改仍留在产品文件中，下一次继续三份比较。

## 接收后检查

1. 查看 `git diff`。`manual_review` 中的依赖、配置、登记和迁移变化需要人工处理。
2. 比较新模板的版本说明。已有数据库必须保留自己的迁移历史，按业务差异新增迁移，
   不能覆盖初始迁移再升级。模板 1.x 到 2.x 的事件、后端选择变化需要单独适配。
3. 首次采用标准包结构时运行 `uv run python ../.agents/skills/fastapi-module/scripts/run_module.py adopt_modules`；目录、固定文件和步骤位置不合格时先处理问题。
   接收上游新增系统功能时，还需按新表声明生成产品自己的迁移。
4. 审查框架差异后运行 `uv run python ../.agents/skills/fastapi-check/scripts/run_check.py framework_lock --update`，
   再运行 `uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs` 和 `uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check`。
5. 使用 PostgreSQL 的产品再加 `--postgres 测试数据库地址`，验证真实模块的接口和业务样例。
6. 接收项目 Skill 与 AGENTS.md 的入口变化，按业务迁移 Skill 逐项推进。首次更新后完整检查；日常局部调试和当前业务共同检查分别运行。


工具不会自动重写依赖与 `uv.lock`，也不会批准不兼容接口或执行迁移。
`framework.lock` 保持原样，确保框架改动仍需要审查。没有共同历史并不妨碍文件比较，
但缺少正确旧模板、业务行为已经不兼容或新版本新增数据库结构时，仍需要人工处理。
未部署的更新可通过产品 Git 分支撤回；数据库迁移和部署需要产品自己的备份与恢复办法。
