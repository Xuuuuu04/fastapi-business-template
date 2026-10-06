---
name: fastapi-docs
description: 业务代码、字段、接口、规则或计划改变后，生成或检查本项目接口和流程文档时使用。
---

# 文档生成

手写业务含义与代码生成结构分开：`doc/模块名/needs.md`、`rules.md`、`changes.md` 由产品维护；字段、接口、表和流程从实际代码生成。模板开发与迁移方法只写在对应 Skill，不在 `doc/` 复制一份。

在 `server/` 执行：

```bash
uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs
uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs --check
```

输出为 `doc/api/`、`modules.md`、`development.md`、`progress.md` 和各业务 `flows.md`。它们表示声明与计划，不证明业务验收或实际执行。检查与运行记录保留在本机目录，避免生成文档携带旧检查结果。

检查生成差异是否符合当前业务，再和源码一起提交。字段含义缺失时修数据模型；规则与样例缺失时修业务文档，不手工改生成结果。没有当前业务包时正常生成空业务视图。
