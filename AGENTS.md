# FastAPI 通用后端模板

## 这个项目是什么

当前是供 AI 开发和迁移业务的模板，只带用户权限和文件管理两个可关闭的通用模块，不带商品、报价等演示业务。采用本模板后，在这里写清具体产品、使用者与主要模块；详细业务放在 [doc/](doc/)。

- 产品：（待填写）
- 使用者：（待填写）
- 主要模块：见 [业务目录](doc/README.md)
- 预先设计：根目录 [项目计划](project-plan.json)，可先列尚未实现的开发包与操作。

## 怎么运行

在 [server/](server/) 下运行：

```bash
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
uv run python -m tools.check
```

配置说明见 [环境样例](server/.env.example)，完整命令见 [后端说明](server/README.md)。开发时用 `tools.check --module 模块名`；它只缩小测试范围，风格、类型、生成文档等检查仍完整。生产使用 PostgreSQL 时加 `--postgres 数据库地址`。每次交付必须完整检查；推送后 [GitHub Actions](.github/workflows/check.yml) 的 PostgreSQL、Redis、S3 与镜像检查也必须通过。

## 目录地图

- [server/service/](server/service/)：固定业务包；入口、步骤与存储各有用途，先看 [业务结构说明](server/service/README.md)。
- [server/shared/](server/shared/)：事务、执行、模块调用、后台任务和运行记录等公共能力。
- [server/app/](server/app/)：模块登记、HTTP 与启动；[server/tools/](server/tools/)：生成、检查与项目阅读入口。
- [server/tests/](server/tests/)：模块、HTTP、框架、质量、安全与恢复测试；[server/migrations/](server/migrations/)：数据库历史。
- [doc/](doc/)：需求、规则、变化、生成的字段/接口/流程及任务；[server/deploy/](server/deploy/)：部署与恢复说明。

## 去哪里找

主代理开工先读摘要，不先展开完整测试记录。下面命令均在 `server/` 执行：

```bash
uv run python -m tools.project --summary --json
uv run python -m tools.project --module file_library --summary --json
uv run python -m tools.project --operation file_library.save_file --json
uv run python -m tools.project --test '准确的pytest测试编号' --json
uv run python -m tools.impact --base origin/main --json
```

摘要列计划缺项、待确认、各数据库检查版本与问题预览；缺项或问题过多时明确省略数量，并给继续读取的入口。单包摘要展开操作与规则样例；已计划但未登记的包也能读取。旧 `tools.project --json` 与 `--module 模块名` 仍提供完整结构，只在需要完整证据时使用。

相关业务从 [doc/README.md](doc/README.md) 找到各包的需求、规则与生成流程；设计见 [开发图](doc/development.md)，规则标注与待确认见 [进度](doc/progress.md)，未完事项见 [任务](doc/tasks.md)。字段含义、接口路径和表结构在生成流程中，不在规则里重复维护。

影响报告列直接修改、传递调用方与后台任务调用方，给出建议检查命令；关闭模块仍在检查范围内。它读取当前声明，删除的历史依赖和系统外调用需要人工确认。建议命令尚未执行，不能据此汇报通过。

## 数据怎么流动

HTTP 或后台任务进入已登记操作，输入由数据模型检查，执行器按流程调用声明读写字段的步骤。数据库与外部动作通过模块存储和公共能力完成；事务按保存步骤安排，先读后写要在保存时用条件修改或加锁读取保护业务规则。

计算写在步骤，步骤在流程中连接，SQL 写在存储中。跨包只用已声明的公开操作或后台任务。计算图来自声明；运行图来自一次实际执行，包含条件、时间、产出形状和 SQL 位置，未知信息保持未知。写法先看 [步骤与事务](server/shared/flow/README.md) 和 [文件管理样板](server/service/file_library/README.md)。

## 本项目的约定

1. 先在业务规则中写编号、异常与确认样例；未确定的标“待确认”，让它进入进度。不要自行补业务含义。新模块用 `tools.new_module 模块名 --title 中文名`，不复制目录。
2. 字段写在数据模型并用 `meaning()` 说明含义；类和关键计算写中文用途。计算步骤声明读写字段，固定业务包的文件位置和依赖方向保持不变。
3. 测试按业务功能集中在对应包。普通规则标注只能说明测试文件提过规则；重要确认样例可在同一规则表增加“样例编号、情况、结果”列，并用 `@pytest.mark.rule_case("模块.R-05-C01")` 对应实际测试。参数化不同样例在各 `pytest.param` 标记；没有当前执行证据、失败或跳过不记为通过。
4. 主代理给局部代理明确修改范围和应得结果；并行工作用独立分支与工作目录。总登记、公共框架和最终生成文档由主代理统一整合，检查共同影响。
5. 修改数据表先升级本地数据库，再生成并人工检查迁移。之后运行 `tools.export_docs`；生成文档与源代码一起提交。后续工作写入任务，业务变化写入本包变化记录。
6. 检查记录保存在本机 [开发记录目录](server/var/development/)，不提交、不进入模板副本。调用方版本包含直接与间接声明依赖；被调用能力改变后，旧调用方检查也过期。规则样例与整轮检查分别判断，全部测试通过仍需要业务验收。
7. 用 `APP_DISABLED_MODULES` 关闭不用的模块，接口与后台入口随之关闭，历史数据保留。新产品用 `tools.start_project`；已有产品更新前看 [版本记录](CHANGELOG.md) 与 [更新说明](server/tools/template/UPGRADING.md)。

## 不要做的事

- 不导入公共入口以外的业务内部文件，不在步骤里直接执行 SQL、调用 HTTP 库或绕过声明的大模型入口。
- 不读写未声明字段，不靠步骤 `return` 传业务结果，不吞异常返回空值或零。
- 不为通过检查改阈值、删检查或删业务文档；不在源码留 TODO 和修错经过。
- 不无意改公共框架、检查或工具；它们由 [框架摘要](server/framework.lock) 保护。本次工作确需修改时，单独说明用途、影响和检查，再审查并更新摘要。
- 不把登记数量、规则标注、历史成功或建议命令写成业务已验收。报告检查、合并、部署和实际使用的不同状态，未验证部分明确保留。

## 已知的坑

- 测试失败先读自动附带的中文运行报告，再按规则确认预期，最后读出错源码。HTTP 错误含 `run_id`；可在 `/system/console`、`/api/system/runs/{run_id}/report` 或 `tools.diagnose run 运行编号` 查看。
- `tools.project --module 模块名 --runs --limit 数量` 明确读取当前配置数据库，显示运行图、产出与 SQL；默认摘要不访问数据库。`--limit` 仅限制数据库运行，不限制完整测试 JSON。近期成功样例覆盖不等同业务验收。
- 旧源码的测试即使通过，也不能证明当前代码。可用 `--checks /分支或CI记录目录` 汇集记录；规则样例表无编号时，样例执行情况未知。
- 不从其他目录复制虚拟环境；移动项目后重新安装，独立测试用 `uv run python -m pytest`，避免旧命令脚本指向原目录。
- 发布前按 [浏览器检查](server/tests/browser/README.md) 检查接口与运行页面，按 [部署说明](server/deploy/README.md) 确认实际环境；后台任务使用用户权限时先读 [任务权限限制](server/shared/jobs/README.md)。
- 本机任务、决定和记录放 `.agents/`，项目专用 Skill 是唯一允许提交的子目录。只读图和命令存在，不代表 Agent 在长任务中始终正确使用。
