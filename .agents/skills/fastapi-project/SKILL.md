---
name: fastapi-project
description: 查看项目计划、业务操作、检查记录、运行记录和改动影响范围时使用。默认只读本地文件，不访问数据库。
---

# 了解项目状态

先看摘要，需要时再展开某个业务、某个操作或某个测试。在 `server/` 执行：

```bash
# 全项目摘要
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --summary --json
# 一个业务包的摘要
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --module 模块名 --summary --json
# 一个操作的详情
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --operation 模块.操作 --json
# 一个测试的详情，要用准确的 pytest 编号
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --test 准确pytest编号 --json
# 当前改动影响哪些地方
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py impact --base origin/main --json
```

## 信息来自哪里

| 信息 | 来源 |
|---|---|
| 计划 | `project-plan.json` |
| 现有结构 | 代码里的声明 |
| 检查结果 | 本机 `server/var/development/checks/` |

摘要会列出：计划里缺了什么、待确认的事、失败的检查、已过期的检查。已计划但还没实现的包也能查。

- 源代码变了，旧的检查结果就过期。失败和跳过的测试不算通过。
- `--checks 目录` 可以把别处保存的检查记录（如 CI 产出）合并进来。

## 查看运行记录

只有加上 `project --module 模块名 --runs --limit 数量`，才会查询当前配置的数据库。`--limit` 只限制运行记录的条数，不限制测试内容。输出包括运行图、每个步骤产出数据的形状和 SQL 所在位置；不保存 SQL 参数和业务数据原文。

## 影响报告

`impact` 对比改动前后的声明，列出：直接修改的部分、间接调用它的部分、用到它的后台任务。已关闭的模块也在范围内。

报告里的"建议检查命令"还没有执行，不能当作已通过。已删除的历史调用和系统之外的调用，仍需人工确认。

## 向用户汇报时

先说哪些操作现在能用、已经检查了什么、还缺什么。不要把登记的操作数、代码量、测试通过率换算成"迁移完成百分之几"。迁移进度用迁移 Skill 里的业务记录，不要另建一份模块配置。
