---
name: fastapi-project
description: 阅读本项目的计划、模块操作、检查证据、运行记录与改动影响时使用；默认摘要不访问数据库。
---

# 项目阅读

先读摘要，需要时再展开操作或准确测试编号。在 `server/` 执行：

```bash
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --summary --json
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --module 模块名 --summary --json
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --operation 模块.操作 --json
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --test 准确pytest编号 --json
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py impact --base origin/main --json
```

计划来自 `project-plan.json`，结构来自代码声明，检查来自本机 `server/var/development/checks/`。摘要说明计划缺项、待确认、失败与过期；未实现但已计划的包也可查询。`--checks 目录` 可汇集独立检查记录。源代码变更使旧结果过期，失败与跳过不记为通过。

只有显式 `project --module 模块名 --runs --limit 数量` 才查询当前配置数据库。`--limit` 限制运行记录，不限制完整测试内容。输出包含运行图、步骤产出形状与 SQL 位置；不保存 SQL 参数或业务结果原文。

影响报告读取改动前后声明，列直接修改、传递调用方及后台任务；关闭模块仍在范围内。建议命令尚未执行。删除的历史调用、系统外调用仍需人工确认。

向用户先说哪项操作现在可用、已检查什么、还缺什么。登记数、代码量和测试通过率不换算成迁移百分比。业务迁移的阶段状态用迁移 Skill 的业务记录，而非再建一份模块配置。
