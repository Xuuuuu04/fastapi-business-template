# FastAPI 通用后端模板

找不到该改哪里时，先在 `server/` 下执行 `uv run python ../.agents/skills/fastapi-project/scripts/run_project.py locate --query "业务词或旧接口路径" --limit 10 --json`，再按结果执行 `project --operation 模块.操作 --json`。定位只读本地声明和规则文档，不访问数据库；旧路径如果没有保留下来，它们的关系就是未知的。

## 这个项目是什么

这是一个给 AI 开发和迁移业务用的后端模板，只有公共框架，没有预置业务。用这个模板做出产品之后，在这里写清楚三件事：产品是什么、谁来用、有哪些主要模块；详细的业务内容放在 [doc/](doc/) 里。

- 产品：（待填写）
- 使用者：（待填写）
- 主要模块：见[业务目录](doc/README.md)
- 提前设计：根目录的[项目计划](project-plan.json)可以先列出还没实现的开发包和操作。

## 怎么运行

进入 [server/](server/) 目录执行：

```bash
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check
```

配置的写法见[环境样例](server/.env.example)。开发时怎么选择检查范围，看[项目检查 Skill](.agents/skills/fastapi-check/SKILL.md)。生产如果使用 PostgreSQL，还要在一个真实的隔离数据库上完整检查一遍。整批交付和发布前跑完整检查；项目配有 GitHub Actions 的话，也要让它通过。

## 目录地图

- [server/service/](server/service/)：业务包，每个包的目录结构是固定的。每个文件做什么，见[业务结构说明](server/service/README.md)。
- [server/shared/](server/shared/)：所有业务共用的框架能力，比如事务、流程执行、模块间调用、后台任务和运行记录。
- [server/app/](server/app/)：模块登记、HTTP 接口和启动。
- [项目 Skill](.agents/skills/fastapi-guide/SKILL.md)：开发方法、脚本和代码模板都在这里。
- [server/tests/](server/tests/)：测试，覆盖模块、HTTP、框架、质量、安全和恢复。
- [server/migrations/](server/migrations/)：数据库迁移历史。
- [doc/](doc/)：需求、规则、变化记录，以及自动生成的字段、接口、流程文档和任务。
- [server/deploy/](server/deploy/)：部署和恢复说明。

## 去哪里找信息

开工时先读本机 `.agents/records/business-state/模块名.md`：先读顶部的生成摘要，再读手写的业务判断、外部依赖和下一步。收工时先更新手写部分，再用 `run_project.py business_state --module 模块名` 刷新生成部分。要读取最近的运行、逾期和待确认情况，需要在确认当前数据库并获得授权后加上 `--runs`；不加这个参数时，这些信息保持未知。生成部分超过 24 小时，或者源码、依赖、声明发生了变化，检查会报错，不会自动刷新。完整的生成明细在同名的 JSON 文件里，默认不展开。这些记录只保存在本机；新代理或新机器首次生成时没有历史，也不要把本机记录当成业务验收或部署状态。

开工先读摘要，不要一上来就展开完整的测试记录。下面的命令都在 `server/` 目录执行：

```bash
# 全项目摘要
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --summary --json
# 一个业务包的摘要
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --module customer_contact --summary --json
# 一个操作的详情
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --operation customer_contact.create_record --json
# 一个测试的详情（要用准确的 pytest 编号）
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py project --test '准确的pytest测试编号' --json
# 当前改动会影响哪些地方
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py impact --base origin/main --json
```

摘要会列出四类信息：计划里还缺什么、哪些事在等人确认、各个数据库的检查是什么版本、当前有什么问题。缺项或问题太多时，摘要会写明省略了多少条，并告诉你去哪里继续看。单个业务包的摘要会展开它的操作和规则样例；已经列入计划但还没登记的包也能查到。

旧的 `fastapi_project.project --json` 和 `--module 模块名` 仍然能给出完整结构，只在需要完整证据时使用。

影响报告会列出：直接修改的部分、间接调用它的部分、用到它的后台任务，并给出建议的检查命令。已经关闭的模块也在统计范围内。报告读取的是当前代码里的声明，所以已经删掉的历史依赖和系统之外的调用，仍然需要人工确认。报告给出的建议命令还没有执行过，不能据此说"通过了"。

业务文档从 [doc/README.md](doc/README.md) 进入，每个业务包都有需求、规则和自动生成的流程文档。整体设计看[开发图](doc/development.md)，规则标注和待确认事项看[进度](doc/progress.md)。没做完的事用现有的产品任务记录，或本机任务记录。字段含义、接口路径、表结构都在自动生成的流程文档里，规则文档里不重复写这些。

如果要迁移旧系统，先读业务现状和[业务迁移 Skill](.agents/skills/fastapi-migration/SKILL.md)。涉及定时或长流程时，先用 new_pipeline 把整条链搭起来，再逐个阶段实现；用 operations drill 按真实规模回放原件、跑通整条链之后，再补局部细节。默认由一个代理从头负责到尾，每完成一项业务，都要做到从输入到页面完整能用；开工前先定好完成条件。依赖顺序只用来安排当前这一项业务，不要求整个项目先把底层全部做完。

## 数据怎么流动

一个请求（HTTP 或后台任务）进入已登记的操作后，输入先由数据模型检查，然后执行器按流程依次调用各个步骤，每个步骤都声明了自己读写哪些字段。数据库和外部动作通过业务包的存储和公共能力完成。事务按"保存步骤"来安排：第一个带 `saves=True` 的步骤开始写事务，最外层操作成功时提交，任何一步失败都回滚。先读后写的场景（比如扣库存、扣余额），在保存时要用条件修改或加锁读取，保证业务规则不被并发破坏。

计算写在步骤里，步骤在流程里连接，SQL 写在存储里。包与包之间只能调用对方声明过的公开操作或后台任务，不能碰内部文件。

文档里有两种图。计算图来自代码里的声明，表示"按设计应该是这样"；运行图来自一次真实运行，包含条件、时间、产出数据的形状和 SQL 的位置，表示"实际发生了什么"。图上不知道的信息会明确标"未知"。写法先看[步骤与事务](server/shared/flow/README.md)和[模块开发 Skill](.agents/skills/fastapi-module/SKILL.md)。

## 本项目的约定

1. **先写规则再写代码。** 先在业务规则文档里写清楚规则编号、异常情况和确认样例；还没定下来的地方标"待确认"，它会出现在进度文档里等着人决定，不要自己补业务含义。新建业务包按[模块开发 Skill](.agents/skills/fastapi-module/SKILL.md) 用命令生成，不要复制已有目录。

2. **字段和注释。** 字段定义写在数据模型里，用 `meaning()` 写含义；类和关键计算写中文用途。计算步骤要声明自己读写的字段。业务包的文件位置和依赖方向保持固定。

3. **测试按业务功能放在对应的包里。** 规则标注只能说明"这个测试文件提到过这条规则"。重要的确认样例，在同一张规则表里加"样例编号、情况、结果"三列，并用 `@pytest.mark.rule_case("模块.R-05-C01")` 对应到具体测试；参数化的不同样例在各自的 `pytest.param` 上标。没有本次运行证据的、失败的、跳过的测试，都不能算通过。

4. **默认一个代理负责到底。** 同一个代理对同一份代码版本和完整的业务结果负责。只有用户或适用的规则明确要求时才分工。共享的接口和数据库变化要一个接一个处理，尽早放在一起验证，不要等所有包都写完才合并。

5. **改数据表的顺序：** 先升级本地数据库，再生成迁移并人工检查，然后按[文档生成 Skill](.agents/skills/fastapi-docs/SKILL.md) 导出文档。flows、rules、changes 和接口文档随源码一起提交；development、modules、progress 三份汇总是生成出来看的，不提交。后续工作写进任务，业务变化写进本包的变化记录。

6. **检查记录只放本机。** 保存在[开发记录目录](server/var/development/)，不提交，也不会进入模板副本。调用方的检查版本包含它直接和间接依赖的声明；被调用的能力一改，旧调用方的检查也算过期。规则样例和整轮检查分开看；全部测试通过，也还需要业务验收。

7. **关闭模块用 `APP_DISABLED_MODULES`。** 关闭后接口和后台入口一起关闭，历史数据保留。新产品用模板管理 Skill 创建；已有产品更新框架前，先看[版本记录](CHANGELOG.md)和[模板管理 Skill](.agents/skills/fastapi-template/SKILL.md)。

## 不要做的事

- 不要导入业务包公共入口以外的内部文件；不要在步骤里直接写 SQL、直接调用 HTTP 库，或绕开声明过的大模型入口。
- 不要读写没声明的字段；不要用步骤的 `return` 传业务结果；不要吞掉异常去返回空值或零。
- 不要为了通过检查去改阈值、删检查或删业务文档；源码里不要留 TODO 和修错的经过。
- 不要随手改公共框架、检查和项目 Skill，它们由[框架摘要](server/framework.lock)保护。确实要改时，单独说明用途、影响和检查，审查后更新摘要。
- 不要把"登记了多少个"、"规则有标注"、"以前成功过"、"建议的命令"说成业务已经验收。检查、合并、部署和实际使用是不同的状态，没验证过的部分要明说。

## 已知的坑

- **测试失败：** 先读自动附带的中文运行报告，再对照规则确认预期，最后才读出错的源码。HTTP 错误里有 `run_id`，可以在 `/system/console`、`/api/system/runs/{run_id}/report` 或 `fastapi_operations.diagnose run 运行编号` 查看这次运行的执行过程。
- **查运行记录：** `fastapi_project.project --module 模块名 --runs --limit 数量` 会明确读取当前配置的数据库，显示运行图、产出和 SQL；默认摘要不访问数据库。`--limit` 只限制数据库里的运行条数，不限制完整测试 JSON。最近成功的样例，不等于业务已经验收。
- **旧源码的测试：** 测试通过也不能证明当前代码是对的。用 `--checks /分支或CI记录目录` 可以汇集别处保存的记录；规则样例表里没有编号时，样例有没有跑过是未知的。
- **虚拟环境：** 不要从别的目录复制。项目移动位置后重新安装。单独运行测试用 `uv run python -m pytest`，避免旧的命令脚本还指向原来的目录。
- **发布前：** 按[浏览器检查](server/tests/browser/README.md)检查接口和运行页面，按[部署说明](server/deploy/README.md)确认实际环境。后台任务要使用用户权限时，先读[任务权限限制](server/shared/jobs/README.md)。
- **本机资料：** 本机的任务、决定和记录放在 `.agents/`，其中只有项目专用 Skill 可以提交。有只读的图和命令，不代表 Agent 在长任务中一直会正确使用它们。

<!-- fastapi-current-state:begin -->
## 当前状态（登记生成）

下面是系统里登记了哪些模块。登记只说明代码里有了它，不代表业务已经完成；
实际运行情况看业务现状档案，或用 project --summary 查询。

- 当前还没有业务模块。新建模块后，这里会自动出现它的登记情况。

想看细节：project --module 模块名 --summary；project --operation 完整操作名。
<!-- fastapi-current-state:end -->
