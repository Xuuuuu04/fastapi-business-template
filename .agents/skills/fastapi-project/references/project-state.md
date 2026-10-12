# 了解项目状态

先看摘要，需要时再往下展开某个业务、某个操作或某个测试。在 `server/` 目录执行：

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

找不到该改哪里时，先在 `server/` 执行 `uv run python ../.agents/skills/fastapi-project/scripts/run_project.py locate --query "业务词或旧接口路径" --limit 10 --json`，再按结果执行 `project --operation 模块.操作 --json`。定位只读本地声明和规则文档，不访问数据库；旧路径如果没有保留下来，它们的关系就是未知的。

## 信息来自哪里

| 信息 | 来源 |
|---|---|
| 计划 | `project-plan.json` |
| 现有结构 | 代码里的声明 |
| 检查结果 | 本机 `server/var/development/checks/` |

摘要会列出：计划里还缺什么、哪些事在等人确认、失败的检查、已经过期的检查。已经列入计划但还没实现的包也能查到。

- 源代码变了，旧的检查结果就过期。失败和跳过的测试不算通过。
- `--checks 目录` 可以把别处保存的检查记录（比如 CI 产出）合并进来。

`project --operation` 会同时列出步骤用到的上游接口协议；计算图展示声明，运行图里的接口名、耗时和状态来自实际调用，旧记录里的接口名保持未知。

## 查看运行记录

只有加上 `project --module 模块名 --runs --limit 数量`，才会查询当前配置的数据库。`--limit` 只限制运行记录的条数，不限制测试内容。输出包括运行图、每个步骤产出数据的形状和 SQL 所在位置；不保存 SQL 参数和业务数据原文。

## 两部分业务现状

档案路径是 `.agents/records/business-state/模块名.md`。开工先读它的生成摘要，不要先展开同名 JSON；收工时更新手写部分。开启的内置运维也会生成 system_ops 现状。

- 生成部分由命令维护，包含：当前模块、流程、定时入口、后台任务模式、最近运行、逾期和待确认，以及观察时间。Markdown 里只放有界的摘要和省略数量，完整明细在同名 JSON 里。源码和依赖版本、声明、生成时刻（24 小时）用来判断是否过期。
- 手写部分由人填写，放三样东西：业务判断、外部依赖、下一步。命令只替换生成标记之间的内容，手写的每一个字节都会完整保留；生成边界损坏时会报错，不会覆盖丢失的判断。不要手改生成摘要或 JSON。

```bash
# 默认不连接数据库，运行状态明确为未知；可以指定单个模块或全项目
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名
# 明确只读当前配置的数据库，生成最近的运行状态；先确认目标环境和授权
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名 --runs
# 只检查是否过期，不读取数据库也不刷新；fastapi-check 的文档检查同样会报过期
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --check
```

`--runs` 只读取编号、状态、数量和时间，不保存业务正文、SQL 参数或连接凭据。最近的历史成功不代表当前源码也成功；没有持久记录也不能证明没有运行过。检查只对观察时刻之前的事实负责，当前数据库之后有没有变化，离线检查是不知道的。生成超过一天、源码/依赖/声明变化、实际观察的库目标/角色/搜索路径变化、或摘要被手改，都会报错；库绑定只保存不含密码的单向摘要，不会泄露连接目标。export_docs 只会初始化或更新过期的声明状态，实际观察仍然要靠 `--runs`。读取数据库失败时不写新状态。这些文件只在本机、不提交；模板副本和新机器需要重新生成；手写判断重要的话，另外记进产品文档或任务，不要只依赖单机记录。

## 影响报告

`impact` 对比改动前后的声明，列出三类内容：直接修改的部分、间接调用它的部分、用到它的后台任务。已经关闭的模块也在范围内。

报告里的"建议检查命令"还没有执行过，不能当作已通过。已经删除的历史调用和系统之外的调用，仍然需要人工确认。

## 向用户汇报时

先说三件事：哪些操作现在能用、已经检查了什么、还缺什么。不要把登记的操作数、代码量、测试通过率换算成"迁移完成百分之几"。迁移进度用迁移 Skill 里的业务记录，不要另建一份模块配置。

单个操作的输出里带查询额度和实际用量：当前额度、最近一次实际测量的运行编号和结果、源码是否还是当前版本；超额失败的记录也保留。没测过或旧记录缺字段时显示未知；默认只读本机测试历史，不读业务库。

## 整合分支与保留证据

在干净的命名分支上执行 `uv run dev merge 分支 --postgres 隔离测试控制连接`。它在本机临时工作树中整合，重新生成明确登记及文档，合并规则和计划，验证增量多头迁移与全新建库，再跑完整双库检查。普通源码、系统路由、手写要求或规则语义存在冲突时停止，保留阶段报告与工作树；原分支不改。`--preview` 只保留通过检查的候选。成功后再次核对原分支和工作区，快进应用并刷新面板。此命令不推送远程，也不升级生产数据库。

```bash
# 固定一轮检查，理由只放本机，不改变原检查结果
uv run dev pin 检查编号 --reason "交付验收原件"
# 清理仅预览，复制输出的preview_id后才可应用
uv run dev gc
uv run dev gc --apply --preview-id 本次预览摘要
```

清理保护任务、审查、交付和文档中的明确编号引用，以及显式固定的检查；每份源码与范围最近三轮、所有失败、旧格式记录也保留。共享轨迹只有在所有保留清单都没有引用时才会清理。发布和清理共用本机锁，原件损坏、链接或预览后变化会报错；普通移动失败恢复原件。旧转换缓存不自动删除。需要解除显式固定时使用 `dev pin 检查编号 --remove`，其他引用仍然有效。
