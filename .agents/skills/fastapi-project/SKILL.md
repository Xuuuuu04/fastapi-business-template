---
name: fastapi-project
description: 管理项目图、规则、任务、文档、离线面板和本机分支整合时使用。运行观察只有显式请求才访问数据库。
---

# 项目与证据

先在 `server/` 执行 `uv run dev status --summary --json`。定位用 `dev locate --query 业务词`，再展开对应包、操作或准确测试编号；不要开工先读整份历史轨迹。

- 项目图包含未实现的计划包；登记和模拟骨架不等于业务完成。
- 开工用 `dev start --package 包 --cases 样例`，收工用 `dev finish --task 编号`；收工必须有本次、当前源码及相关链的实际证据。
- 规则用 `dev rules` 管理，明确确认引用原话与独立样例；代码、历史文档和测试成功不能变成人类确认。
- `dev panel` 生成纯本机离线页面。颜色来自证据，建议命令和未来计划保持未执行状态。

按当前任务展开：

| 情况 | 参考 |
| --- | --- |
| 项目摘要、业务现状、任务、影响、整合、证据固定与清理 | [项目状态](references/project-state.md) |
| 声明文档生成与检查、手写段保留 | [文档生成](references/documents.md) |
| 从独立样例到真实实现：骨架、开工、收工、复核材料、契约修改请求 | [填空开发](references/task-development.md) |
| 离线面板的状态颜色、证据来源和各区块含义 | [开发面板](references/panel.md) |

生成文档执行 `uv run dev docs`；只比较用 `uv run dev docs --check`。规则和变化记录只更新账本生成段，原文及确认语义仍由业务资料维护。

`dev merge 分支 --postgres 隔离控制连接` 在临时工作树中整合和实际验证，成功后核对原分支再应用。生产数据库不参与。清理默认 `dev gc` 预览，`dev pin` 固定引用；新原件或引用变化后旧预览不能应用。

需要运行状态时才用 `status --module 包 --runs --limit 数量`，先确认实际数据库和授权。其余摘要与定位只读本机声明。检查通过、合并成功、部署和业务验收分别汇报。
