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

找不到该改哪里时，先在 `server/` 执行 `uv run python ../.agents/skills/fastapi-project/scripts/run_project.py locate --query "业务词或旧接口路径" --limit 10 --json`，再按结果执行 `project --operation 模块.操作 --json`。定位只读本地声明和规则文档，不访问数据库；未保留的旧路径关系未知。

## 信息来自哪里

| 信息 | 来源 |
|---|---|
| 计划 | `project-plan.json` |
| 现有结构 | 代码里的声明 |
| 检查结果 | 本机 `server/var/development/checks/` |

摘要会列出：计划里缺了什么、待确认的事、失败的检查、已过期的检查。已计划但还没实现的包也能查。

- 源代码变了，旧的检查结果就过期。失败和跳过的测试不算通过。
- `--checks 目录` 可以把别处保存的检查记录（如 CI 产出）合并进来。

`project --operation`同时列出步骤使用的上游Endpoint协议；计算图展示声明，
运行图中的接口名/耗时/状态来自实际调用，旧记录接口名保持未知。

## 查看运行记录

只有加上 `project --module 模块名 --runs --limit 数量`，才会查询当前配置的数据库。`--limit` 只限制运行记录的条数，不限制测试内容。输出包括运行图、每个步骤产出数据的形状和 SQL 所在位置；不保存 SQL 参数和业务数据原文。

## 两部分业务现状

路径 `.agents/records/business-state/模块名.md`，开工先读摘要，不先展开同名JSON；收工更新。开启的内置运维也生成system_ops现状。

- 生成部分：当前模块、流程、定时入口、后台任务模式、最近运行/逾期/待确认与观察时间。Markdown只放有界摘要和省略量，同名JSON保留完整生成明细；源码和依赖版本、声明、生成时刻（24小时）用于判断过期。
- 手写部分：业务判断、外部依赖、下一步。命令只替换生成标记内的内容，完整保留外部手写字节；生成边界损坏报错，不覆盖丢失判断。不要手改生成摘要或JSON。

```bash
# 默认不连接DB，运行状态明确未知；指定模块或全项目
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名
# 明确只读当前配置DB，生成最近状态；先确认目标与授权
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名 --runs
# 只检查，不读取DB也不刷新；fastapi-check的文档检查同样报过期
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --check
```

--runs只读编号/状态/数量/时间，不保存业务正文、SQL参数或连接凭据。最近历史成功不是当前源码成功；无持久记录不证明没运行。检查对观察时刻之前的事实负责，当前DB是否已经变化不能由离线检查得知。生成超过一天、源码/依赖/声明变化、实际观察的库目标/角色/搜索路径变化或摘要被手改报错；库绑定只存无密码的单向摘要，不泄露连接目标。export_docs只初始化/更新过期的声明状态，实际观察仍需--runs。读取DB失败不写新状态。文件本机不提交，模板副本/新机器需重新生成；手写判断重要时另记产品文档/任务，不依赖单机记录作为唯一资料。

## 影响报告

`impact` 对比改动前后的声明，列出：直接修改的部分、间接调用它的部分、用到它的后台任务。已关闭的模块也在范围内。

报告里的"建议检查命令"还没有执行，不能当作已通过。已删除的历史调用和系统之外的调用，仍需人工确认。

## 向用户汇报时

先说哪些操作现在能用、已经检查了什么、还缺什么。不要把登记的操作数、代码量、测试通过率换算成"迁移完成百分之几"。迁移进度用迁移 Skill 里的业务记录，不要另建一份模块配置。

单操作输出query_budget和query_actual：当前额度、最近实际测量的运行号/结果/源码是否当前；超额失败也保留。没测过或旧记录缺字段显示未知；默认只读本机测试历史，不读业务库。
