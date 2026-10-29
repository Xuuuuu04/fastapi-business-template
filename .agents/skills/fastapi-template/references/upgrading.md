# 升级框架

更新工具只比较框架文件（清单在 `server/shared/modules/validation/framework_files.py`），不要求产品和模板有共同的 Git 历史。业务包、模块登记、环境配置、依赖版本、迁移历史和业务文档都由产品自己保留。

## 一、准备旧模板和新模板

先提交产品当前的改动。产品根目录的 `template-source.json` 记着上次采用的模板版本和提交，按它取出旧模板，不要猜：

```bash
git clone https://github.com/Xuuuuu04/fastapi-business-template.git /tmp/template-upgrade
git -C /tmp/template-upgrade worktree add --detach /tmp/template-old 旧模板提交
git -C /tmp/template-upgrade worktree add --detach /tmp/template-new 新模板提交
```

## 二、预览和写入

在新模板的 `server/` 下运行，用的是新版本的工具和框架清单：

```bash
cd /tmp/template-new/server
uv sync
uv run dev upgrade --target /产品目录 --base /tmp/template-old --source /tmp/template-new
uv run dev upgrade --target /产品目录 --base /tmp/template-old --source /tmp/template-new --apply
```

预览结果里，`changes` 是要改的框架文件，`newly_managed` 是新版本才开始管理的文件，`manual_review` 是要人工处理的依赖、配置和登记。

| 情况 | 处理 |
| --- | --- |
| 产品没改过这个文件 | 直接用新版 |
| 产品和新版改的是不同位置 | 自动合并文本 |
| 同一处两边都改了，或一边删一边改 | 冲突 |

有冲突时一个文件都不写。按业务规则和接口含义人工解决冲突，再重新预览。写入后 `template-source.json` 更新成新模板。

## 三、写入之后

1. 看 `git diff`，按 `manual_review` 处理依赖、配置和登记；依赖变了重新生成 `uv.lock`。
2. 新版增加了框架表时，在产品的迁移链上新增迁移，不改已有迁移。
3. 运行 `uv run dev docs` 和 `uv run dev check`，生产用 PostgreSQL 的再加 `--postgres 测试库地址` 跑一次。
4. 提交。要撤回就用 Git 撤回这次提交。
