# 主代理批量开发指南

一次迁移或开发多个开发包（例如旧系统 20 多个包、20 万行级）时，主代理在规划前先读本文。
只做一个包的小改按 [AGENTS.md](../AGENTS.md) 的常规流程，不必展开这里的分层与并行。

## 目标与分工

目标：每个包的接口和规则样例齐全，按依赖自下而上逐层推进，一层通过后再开下一层，主干始终可用。

| 谁 | 负责 |
| --- | --- |
| 主代理 | 依赖规划与分层、公共登记（`server/app/setup/catalog.py`、`server/app/api/routers.py`）、合并、每层整体检查、生成文档统一导出、与用户确认未定的业务规则 |
| 子代理 | 分配到的单个开发包或明确文件范围；独立 worktree 与独立分支；只跑自己包的快速检查；返回改动、检查结果、证据位置和未解决问题 |

子代理不合并代码、不改公共登记、不动其他包、不导出全局生成文档。这些由主代理统一做。

## 先读现有资料，不新建第二份配置

开发图用现有计划与工具生成，不另外维护一份依赖或层的配置。

```bash
uv run python -m tools.project --summary --json                    # 业务线、开发包、缺项、待确认、最近检查
uv run python -m tools.project --module 模块名 --summary --json    # 单包操作、规则样例、依赖
uv run python -m tools.project --operation 模块.操作 --json        # 单操作步骤、条件和最近执行
uv run python -m tools.impact --base origin/main --json            # 直接修改、调用方与建议检查
```

- `project-plan.json` 记录业务线、开发包、标题和预期公开操作；`tools.export_docs` 据此生成 `doc/development.md`。
- 依赖方向来自声明的公开操作调用，可从摘要里的 `dependencies` 和 `doc/modules.md` 的模块关系图读取，不必手写。
- `project-plan.json` 目前只支持 `module`、`title`、`operations`。依赖、层、验收样例和观察入口不写进这个文件，也不要假定它有新字段；它们写在下面说的任务进度里。

## 分层规划（自下而上）

- 被别的包调用的底层包先做；同一层里的包之间没有互相调用。
- 规划表列：开发包 / 公开操作 / 依赖（调用了谁）/ 层 / 验收样例 / 观察入口。这张表是分工用的工作记录，写在 `.agents/tasks/<任务名>.md`，不进入提交。
- 包登记后，依赖和观察入口可以用 `tools.project` 重新读取，不用在表里重复维护。
- 依赖方向不明确时先问用户或在规划里标“待确认”，不要靠猜决定先做谁。

观察入口指一次真实运行怎么看：对应的接口路径或后台任务，加 `/system/console`、`/api/system/runs/{run_id}/report` 或 `tools.diagnose run 运行编号`。

## 并行开发与隔离

- 每个并行子代理用一个独立 worktree 和一个独立分支；主代理已建好 worktree 时沿用。
- 各自独立的虚拟环境；测试数据库也各自独立。不要共用虚拟环境，也不要对同一个 PostgreSQL 测试库并行运行会建表删表的测试。
- 并行数量按同层独立包的数量、当前工具可用的容量或限额、上一轮实际返工和耗时来定，不默认全部铺开。先小批试跑一两个包，看质量和返工情况再决定加不加。
- 模型按本次实际可用的能力说明和实测结果选（响应速度、返工次数、剩余额度），需要时可先问用户推荐。不要把型号排名或提供商固定写进项目文档。

## 子代理每个包的应得结果

- 固定目录结构、公开操作、接口（HTTP 路由或后台任务）、业务文档（needs.md、rules.md、changes.md）和规则样例都不省略。
- 规则写进 rules.md 并编号，测试用 `@pytest.mark.rule_case("模块.R-xx-C01")` 对应实际用例；没定的规则在 rules.md 标“待确认”，由它进入 [progress.md](progress.md)。
- 旧行为兼容样例以一个固定的旧版本为准（记下旧版本号或提交），测试预期来自它；业务是否正确另看规则。
- 外部动作（HTTP、邮件、支付、第三方接口）在测试里隔离，不真实调用，用记录样例或替身。
- 子代理自检只跑自己包：`uv run python -m tools.check --quick --module 本包`（见“检查入口”）。这是快速、非完整的检查，不能当作正式通过。
- 返回内容：改了什么、跑了哪些检查及结果、证据位置（测试编号或运行编号）、未解决的问题、需要主代理决定的点。

## 整层验收（主代理）

一层里的包都合并到主干后再整层检查：先对每个包正式单包检查 `uv run python -m tools.check --module 包`，再做整层检查（受影响模块一起检查，或按改动范围检查）。

层验收标准：

- 必须修：影响金额、重要数据、权限或旧接口兼容的失败；公共登记或框架检查失败；整层测试失败。
- 有明确记录并被接受代价才推进：其他不影响业务结果的问题，先在 `.agents/tasks/<任务名>.md` 或 [tasks.md](tasks.md) 记下问题、影响和接受的代价，再进入下一层。
- “bug 差不多就行”不算通过；没有实际运行的检查不称通过。

一层排查干净再开下一层。发现依赖方向判断错了，先改规划和按依赖排的顺序，再继续。

## 检查入口

现在可用：

```bash
uv run python -m tools.check                          # 完整检查
uv run python -m tools.check --module 模块名          # 单包测试，其余检查仍完整
uv run python -m tools.check --postgres 连接地址      # 在 PostgreSQL 上再跑一遍测试
```

`--module` 多值、`--quick`、`--affected` 是批量开发追加的检查方式；在实现并验证可用之前，先按现有单值写法和完整检查执行。

- `--module A --module B` 或 `--module A,B`：一次检查多个包，其余检查仍完整。
- `--quick --module A`：只做局部代码风格、格式和所选测试，不做完整类型检查和生成文档检查；结果记为“快速、非完整”。
- `--affected --base origin/main`：取改动前后依赖的并集，只检查受影响的模块；公共改动或影响范围不明确时退回完整检查。
- `--postgres 连接地址` 可以和上面组合。

“交付完整检查”指整批交付或发布前跑完整检查，不是每个文件、每次本地提交都要完整检查。

## 公共登记与合并

- 新包会改动 `server/app/setup/catalog.py` 和 `server/app/api/routers.py`，属于公共登记，由主代理统一修改并检查登记是否完整。
- 合并前跑导入与依赖检查、登记检查（`server/tests/architecture` 里的导入和登记用例），确认 `tools.project --summary` 没有缺项。
- 改动 `framework.lock` 覆盖的框架文件时单独说明用途、影响和检查，再运行 `uv run python -m tools.framework_lock --update`；业务开发不要顺手改框架。
- 生成文档由主代理统一运行 `uv run python -m tools.export_docs`，各包不单独导出。
- 合并到主干后再跑整层或完整检查，通过后才进入下一层。

## 记录

- 进度写 `.agents/tasks/<任务名>.md`（超过 60 行就压缩）；决定写 `.agents/decisions.md`；完成摘要写 `.agents/done.md`。
- 检查记录留在本机 `server/var/development/`，不提交；调用方或公共能力变化后，旧记录不再代表当前代码。
