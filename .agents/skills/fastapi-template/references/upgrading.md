# 升级框架

更新工具只比较框架文件（清单在 `server/shared/modules/validation/framework_files.py`），不要求产品和模板有共同的 Git 历史。业务包、模块登记、环境配置、依赖版本、迁移历史和业务文档由产品自己维护，工具不碰。

## 一、准备旧模板和新模板

先提交产品当前的改动，并清理或确认尚未结束的外部请求和旧版流程任务：结果尚待确认的外部请求留待查询核实，不要直接重发；如果新版调整了内置 Data 的中文说明，已有的旧流程可能因格式摘要变化而暂停等待人工核对。产品根目录的 `template-source.json` 记着上次采用的模板版本和提交号，按它取出旧模板：

```bash
git clone https://github.com/mumuxsy/fastapi-business-template.git /tmp/template-upgrade
git -C /tmp/template-upgrade worktree add --detach /tmp/template-old 旧模板提交
git -C /tmp/template-upgrade worktree add --detach /tmp/template-new 新模板提交
```

## 二、预览和写入

在新模板的 `server/` 下运行，工具会使用新版本的校验器与框架文件清单：

```bash
cd /tmp/template-new/server
uv sync
uv run dev upgrade --target /产品目录 --base /tmp/template-old --source /tmp/template-new
uv run dev upgrade --target /产品目录 --base /tmp/template-old --source /tmp/template-new --apply
```

预览结果中，`changes` 列出待更新的框架文件，`newly_managed` 列出新版本开始管理的文件，`manual_review` 列出需要人工处理的依赖、配置和模块登记。

| 情况 | 处理方式 |
| --- | --- |
| 产品没改过这个文件 | 直接替换为新版本 |
| 产品和新版改的是不同位置 | 自动合并文本 |
| 同一处两边都改了，或一边删除、一边修改 | 标记冲突并中止写入 |

遇到冲突时工具一个文件都不写；你需要按业务规则和接口含义手工解决冲突后再预览，确认无误再加 `--apply`，完成后工具会在 `template-source.json` 写入新模板版本。

## 三、写入之后

1. **处理配置、工作流与 `manual_review` 清单**。升级工具不覆盖产品自己的 `.github/`、`AGENTS.md` 和部署配置，手动对照新模板里的 PR 模板、`check.yml`（使用 `dev check --delivery`）和状态模型工作流；依赖变更时重新生成 `uv.lock`。
2. **补充框架表迁移与映射摘要**。如果新版增加了框架表，在产品的迁移链上新增一条迁移，不要修改已有迁移；如果产品调整了任务状态函数，先核对状态模型、真实回归测试与源码映射再更新摘要。
3. **跑通验证并提交**。执行 `uv run dev docs` 和 `uv run dev check`（使用 PostgreSQL 的再跑 `--postgres 测试库地址`），确认全部通过后提交；需要回退时用 Git 撤销这次提交即可。
