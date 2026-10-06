# 已有产品接收框架更新

适用于：复制模板、或通过 GitHub 模板创建、因此和模板没有共同 Git 历史的产品。

更新工具只比较框架文件，不要求把模板的全部提交合并进产品。业务包、模块登记、业务文档、项目计划、环境配置、依赖版本和数据库迁移历史，都由产品自己保留。

## 一、准备旧模板和新模板

先把产品当前的工作保存好，新开一个分支。

用初始化工具创建的产品，`template-source.json` 记录了上次采用的模板版本、Git 提交和文件摘要，据此取出旧模板。没用初始化工具的旧产品，要从第一次复制模板时的提交或版本取出。不能随便猜一个版本当旧模板，否则工具分不清哪些是产品自己改的。

```bash
git clone https://github.com/Xuuuuu04/fastapi-business-template.git /tmp/template-upgrade
git -C /tmp/template-upgrade worktree add --detach /tmp/template-old 旧模板提交或标签
git -C /tmp/template-upgrade worktree add --detach /tmp/template-new 新模板提交或标签
```

旧产品里还没有更新工具时，在新模板的 `server/` 下运行，并指定产品目录：

```bash
uv sync
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --target /产品目录 \
  --base /tmp/template-old --source /tmp/template-new
```

确认预览没问题后，在同一条命令末尾加 `--apply`。不加就不会写入产品。

## 二、预览和接收

产品里已经有更新工具时，在产品自己的 `server/` 下运行：

```bash
# 预览
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /tmp/template-old --source /tmp/template-new
# 确认后写入
uv run python ../.agents/skills/fastapi-template/scripts/run_template.py update_framework --base /tmp/template-old --source /tmp/template-new --apply
```

工具对每个文件这样处理：

| 情况 | 处理 |
|---|---|
| 产品没改过这个文件 | 直接用新版 |
| 产品和新版改的是不同位置 | 尝试自动合并文本 |
| 同一处两边都改了 | 冲突 |
| 新增的文件和产品里的文件重名 | 冲突 |
| 新版删了产品改过的文件 | 冲突 |
| 产品删了新版改过的文件 | 冲突 |

- 有任何一个冲突，所有文件都保持原样，一个都不写。
- 默认只预览。`--apply` 在保存前会再检查一次，保存中途失败会恢复本次已写入的文件。
- 文件链接、或路径指到项目之外的文件会被拒绝。
- 工具从不访问或修改数据库。

冲突要人工解决，以业务规则和接口含义为准，改完重新预览。更新完成后，`template-source.json` 会记下新模板的文件摘要。产品自己的修改仍保留在产品文件里，下次更新继续做三份比较。

## 三、接收之后检查

1. 看 `git diff`。预览结果里 `manual_review` 列出的依赖、配置、登记和迁移变化，需要人工处理。
2. 读新模板的版本说明。已有的数据库必须保留自己的迁移历史，按业务差异新增迁移，不能覆盖初始迁移再升级。模板从 1.x 升到 2.x 时，事件和后端选择有变化，需要单独适配。
3. 第一次采用标准包结构时，运行 `uv run python ../.agents/skills/fastapi-module/scripts/run_module.py adopt_modules`。目录、固定文件、步骤位置不合格的，先处理。新版增加了系统功能和新表时，还要按新表的声明生成产品自己的迁移。
4. 审查完框架差异，依次运行：
   - `uv run python ../.agents/skills/fastapi-check/scripts/run_check.py framework_lock --update`
   - `uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs`
   - `uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check`
5. 使用 PostgreSQL 的产品，检查命令再加 `--postgres 测试数据库地址`，用真实业务包验证接口和业务样例。
6. 接收项目 Skill 和 `AGENTS.md` 的变化，之后按业务迁移 Skill 逐项推进。第一次更新后跑完整检查；日常的局部调试和当前业务的联合检查另外分开运行。

## 工具不做的事

- 不改依赖和 `uv.lock`。
- 不批准不兼容的接口，不执行数据库迁移。
- 不改 `framework.lock`，所以框架改动仍然需要人审查。

没有共同 Git 历史不妨碍比较文件。但旧模板找不对、业务行为已经和新版不兼容、新版新增了数据库结构，这些情况仍要人工处理。

还没部署的更新，用产品的 Git 分支撤回。数据库迁移和部署需要产品自己的备份和恢复办法。
