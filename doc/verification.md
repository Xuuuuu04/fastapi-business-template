# 分层检查与验证指南

这份说明介绍如何在日常开发、提交审查和上线前按最小必要范围验证后端改动。详细的测试分组与命令行说明见 [检查技能](../.agents/skills/fastapi-check/SKILL.md)、[测试说明](../.agents/skills/fastapi-check/references/tests.md)、[隔离验收](../.agents/skills/fastapi-check/references/acceptance.md) 和 [状态模型检查](../.agents/skills/fastapi-check/references/job-model.md)。

## 日常检查层次

所有命令都在 `server/` 目录下执行：

| 时机 | 命令 | 检查内容 |
| --- | --- | --- |
| 调试单个包 | `uv run dev check --quick --module 包名` | 代码规范、导入边界、本包单测与集成测试（跳过全仓类型与文风，反馈最快） |
| 提交单包改动前 | `uv run dev check --module 包名` | 加上全仓 `mypy` 类型检查、架构规则与文档文风检查 |
| 按分支差异选包 | `uv run dev check --affected --base origin/main` | 自动分析 Git 差异波及的业务包与调用方并运行对应检查 |
| 修改公共代码或批量提交 | `uv run dev check` | 全仓静态规则、架构测试、框架测试及所有已登记操作的覆盖核验 |
| 交付与 CI 终检 | `uv run dev check --delivery` | 在全量检查基础上拦截尚未实现的 `placeholder=True` 和测试专用的 `simulated=True` 步骤 |
| PostgreSQL 实测 | `uv run dev check --postgres postgresql+psycopg://...` | 验证真实行级锁、唯一冲突、`ExactNumber` 数值精度与并发恢复 |

运行全仓检查时，应用里登记的每一个公开操作都必须至少被测试实际执行过一次，否则检查会直接列出漏测操作并报错。

## 真实跑一次操作

写完代码或排错时，可以在本地开发库上直接运行指定操作并查看完整步骤报告：

```bash
cd server
uv run dev run 包名.操作名 --input '{"字段": "值"}' --allow-write
```

命令会输出每一步的耗时、读写字段摘要、数据库查询次数以及最终结果；不加 `--allow-write` 时拒绝执行写入类操作，防止误改本地数据。

## 前后端隔离验收与形式化验证

- **隔离 HTTP 验收服务**：运行 `uv run dev acceptance-server --port 0 --run-id 本轮编号` 会在独立临时目录创建全新 SQLite 实例并启动单轮真实 HTTP 服务，配合前端 Playwright 跑通端到端业务场景，退出时自动清理临时数据。
- **后台任务状态模型（TLA+）**：修改后台任务领取、租约超时接管或提交回滚逻辑时，运行 `uv run dev verify-model`（可选加 `--jar /绝对路径/tla2tools-1.7.4.jar` 调用本地 TLC），同时验证状态机不变量、故意注入缺陷的反例捕获以及真实代码回归。
