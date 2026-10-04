# 项目说明（AI 开发者先读这里）

## 1. 产品业务

> 用模板开发具体产品时，在这里用三到五句话写清：产品叫什么、给谁用、解决什么问题、有哪些主要模块。详细业务写在 `doc/`，不要写在这里。

- 产品：（待填写）
- 使用者：（待填写）
- 主要模块：见 [doc/README.md](doc/README.md)

当前仓库是供 AI 开发和迁移业务的模板，只带用户权限和文件管理两个可关闭的通用模块；不带商品、报价等演示业务。

## 2. 开工前按顺序读

1. `uv run python -m tools.project --json`：一次取得业务线、开发包、模块结构与真实测试情况。
   [doc/development.md](doc/development.md)、[doc/progress.md](doc/progress.md) 和 [doc/tasks.md](doc/tasks.md)：设计、规则与未完事项。
2. [doc/README.md](doc/README.md) 和相关模块的 `needs.md`、`rules.md`、`flows.md`：业务是什么、规则怎么算；字段含义、接口路径、数据表在自动生成的 `flows.md` 中。
3. [server/service/README.md](server/service/README.md)：模块的固定结构和必须遵守的规则。
4. 一个完整模块：[server/service/file_library/](server/service/file_library/) 的 README、`flow.py`、`steps/`。
5. [server/shared/flow/README.md](server/shared/flow/README.md)：步骤怎样写、事务怎样安排。

用 `APP_DISABLED_MODULES` 关闭不需要的业务模块，接口与后台入口随模块一起关闭，历史数据保留。旧项目升级前先读 [CHANGELOG.md](CHANGELOG.md) 的不兼容变化；模块协作使用明确调用或后台任务，存储和缓存使用内置实现。

不需要通读全部代码。每个目录都有 README，先读 README 再决定读哪个文件。

## 3. 开发一个功能

1. **先改业务文档**：在 `doc/模块名/rules.md` 写清规则、编号、异常情况和确认样例；没有确认的写“待确认”，不要自己补全业务规则。字段含义写在代码的 `meaning()` 中，不在 `rules.md` 重复。预先设计的业务线、开发包和操作写在根目录 `project-plan.json`，可以先列出未实现的目标。
2. **新模块用命令生成**：`uv run python -m tools.new_module 模块名 --title 中文名`，不要手工复制目录。
3. **按固定结构写**：字段写在 `data.py` 并用 `meaning()` 写含义；每个类写中文用途说明；计算写成步骤，声明读写的字段；步骤在 `flow.py` 中连成流程；数据库访问写在 `store/`。
4. **写测试**：生成器已提供步骤和接口测试，按业务功能集中在对应模块目录中，不到处新建测试文件；用 `uv run python -m tools.check --module 模块名` 单独检查。规则测试的预期值来自 `rules.md` 的确认样例，测试说明中写上规则编号（例如 `# R-03：……`），`doc/progress.md` 按编号统计规则有没有测试；接口测试从 HTTP 入口进入。
5. **生成迁移和文档**：先 `uv run alembic upgrade head` 把本地数据库升到最新，再 `uv run alembic revision --autogenerate -m "说明"`（检查生成结果），最后 `uv run python -m tools.export_docs`（更新 `doc/` 下的流程、接口描述和进度，一起提交）。
6. **记录没做完的事**：留到以后的工作写进 `doc/tasks.md`，完成的勾选；用 `uv run python -m tools.impact --base origin/main` 查看这次改动影响了什么。
7. **全量检查**：在 `server/` 运行 `uv run python -m tools.check`，全部通过才算完成。推送后 GitHub Actions（`.github/workflows/check.yml`）会在 PostgreSQL、Redis、S3 服务上重跑同一检查并生成部署镜像，也必须通过。

## 4. 不能做的事

| 不要做 | 原因 |
| --- | --- |
| 业务代码导入 `shared` 下 `public.py` 以外的文件，或导入其他模块 `public.py` 以外的文件 | 模块之间只靠约定连接，内部才能随时重构 |
| 在步骤里直接写 SQL、调用 HTTP 库，或绕过 `model` 参数调用大模型 | 数据访问、外部调用必须经过框架，才能记录、限流、控制事务 |
| 读写没有声明的字段，或把结果 `return` 出来 | 字段来源图依赖读写声明 |
| 用 `try/except` 吞掉异常后返回空值或零，或加没有必要的防御代码 | 错误要在运行记录中看得见，悄悄变成零的结果最难排查 |
| 留 TODO、写修错经过的注释 | 未完成的事写进 `doc/tasks.md`，修改经过写进提交说明 |
| 为了通过检查修改阈值、删检查、删业务文档内容 | 检查失败说明结构有问题，应该改代码或整理文档 |
| 修改 `shared/`、`tools/`、`app/setup/`、检查规则等框架文件 | 这些受 `server/framework.lock` 保护；确需修改时单独说明原因，交给人审查 |

## 5. 出问题怎样查

1. 测试失败时，失败输出中已附上失败运行的中文报告：停在哪一步、为什么、源码位置、每一步写了什么，先读它。
   手动调用接口出错时，错误响应里有 `run_id`，可在 `/system/console` 查看步骤、上下层调用和耗时；运行 `uv run python -m tools.diagnose run 运行编号`（本地默认把运行记录写进 SQLite）或调用 `/api/system/runs/{run_id}/report`。
2. 按报告中的规则编号读 `rules.md`，确认预期。
3. 不要从其他目录复制 `.venv`；移动项目后重新安装依赖。单独执行检查时使用 `uv run python -m pytest`，避免旧命令脚本仍指向原目录。
4. 再读出错位置的源码和测试。不要一开始就从头读代码，也不要写临时脚本到处试。

## 6. 完成时怎样汇报

发布前还需按 [server/tests/browser/README.md](server/tests/browser/README.md) 检查接口文档和运行页面；生产配置验收范围见 [server/deploy/README.md](server/deploy/README.md)。

部署检查只要求启用模块实际使用的配置。迁入用户后台任务前，先读 [server/shared/jobs/README.md](server/shared/jobs/README.md) 的权限限制，并在业务规则中确定执行时的用户状态检查。

说明改了什么、对应哪些业务规则、`tools.check` 的结果（是否在 PostgreSQL 上运行过）、还有哪些没有验证。需要人决定的业务问题单独列出，不要自行假设；同时写进对应 `rules.md` 并标“待确认”，让它出现在 `doc/progress.md` 中。合并请求按 `.github/pull_request_template.md` 填写。

检查轮次保存在本机 `server/var/development/`，不提交；代码改变后旧结果标为过期。模块详情用 `tools.project --module 模块名`。
新产品用 `tools.start_project` 生成干净副本，已有产品的框架更新步骤见 [UPGRADING](server/tools/template/UPGRADING.md)。
默认启动检查固定文件位置、步骤函数位置、依赖方向和框架摘要；旧项目用 `tools.adopt_modules` 采用标准结构。
`tools.project --module 模块名 --runs` 显示运行图、字段产出、SQL 耗时和存储函数位置；近期样例覆盖不等同业务验收。
`.agents/` 是本机协作资料；项目专用 Skill 是唯一允许提交的子目录。
