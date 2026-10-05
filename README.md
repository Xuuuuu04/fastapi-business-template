# FastAPI 通用后端模板

当前代码版本 2.0.0（未发布），变化见 [CHANGELOG.md](CHANGELOG.md)。

方便 AI 开发和迁移业务的单体后端模板：人审查业务和架构，AI 按固定结构逐个模块开发或迁移旧系统；运行时记录执行过程，可以按编号查询中文报告，定位步骤、字段、规则和源码位置。记录保存失败时会显示不完整，业务结果仍以业务数据为准。

## 目录

| 目录 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | AI 开发者的入口：阅读顺序、开发步骤、禁止事项、排查方法 |
| [server/](server/) | 后端代码、测试、迁移、部署 |
| [doc/](doc/) | 业务文档：需求、规则、变化记录；自动生成的流程、接口描述、开发进度；任务清单 |
| [design/](design/) | 模板自身的设计记录；用模板开发产品时可以删除 |
| [.github/](.github/) | 持续集成与依赖更新，见下方“持续集成” |

## 快速开始

```bash
cd server
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

打开 http://127.0.0.1:8000/docs 。更多命令见 [server/README.md](server/README.md)。

## 用这个模板开始新项目

1. 在模板的 `server/` 下运行 `uv run python -m tools.start_project /新项目目录 --name 产品名称`。
   它创建干净副本，重新生成产品入口、任务与空业务计划，不复制模板讨论、验收、环境、数据库或测试历史。
   也可先在 GitHub 上点“Use this template”建立仓库，再从该副本运行初始化并提交生成的新产品。
2. 模板只保留用户权限和文件管理两个通用模块，不需要时在配置中设置 `APP_DISABLED_MODULES=["user_access","file_library"]`；代码和历史数据保留，接口与执行入口一起关闭。
3. 在 [项目入口](AGENTS.md#这个项目是什么) 写清产品名称、使用者和主要模块。
4. 每个业务模块先运行 `uv run python -m tools.new_module 模块名 --title 中文名` 生成固定目录和测试，再在本包业务说明中写清真实需求和规则，按 [项目约定](AGENTS.md#本项目的约定) 开发。
5. 开发时用 `uv run python -m tools.check --module 模块名` 单独检查；每次完成后运行 `uv run python -m tools.check`；生产使用 PostgreSQL 时加 `--postgres 数据库地址`。

## 一次查看开发状态

先在 [project-plan.json](project-plan.json) 写产品名称、业务线、开发包与预期操作，未实现的开发包也可先列入。
分组只用于理解和分工，`service/模块名` 的代码位置保持一致。
下面的命令在 `server/` 下运行。

```bash
uv run python -m tools.project --summary --json         # 主代理先看缺项、待确认、失败与过期
uv run python -m tools.project --module file_library --summary --json # 单包操作与确认样例
uv run python -m tools.project --operation file_library.save_file --json # 单操作步骤与证据
uv run python -m tools.project --test '准确pytest测试编号' --json # 单测试最近记录
uv run python -m tools.impact --base origin/main --json  # 直接修改、调用方与建议检查
uv run python -m tools.project --json                   # 保留旧完整入口，按需使用
uv run python -m tools.project --runs --limit 10         # 明确读取配置数据库，默认不读取
```

[doc/development.md](doc/development.md) 是可提交的设计与结构视图。
`tools.check` 每轮保存实际结果到本机 `server/var/development/checks/`，支持模块测试和不同数据库；
源码改动后旧结果显示过期。登记比例与测试成功执行比例分别计算，不等同于业务验收；
没有设计目标时比例未知。`--runs` 比较真实源码摘要，计算近期成功样例覆盖，并保留旧版本记录；
未执行的操作是否正确仍未知。主干 Agent 可用 `--checks /分支检查目录` 汇集其他 Agent 或 CI 的检查，生成的下一步命令保留这些目录。
摘要只预览少量问题和缺项，保留准确数量与省略数量；完整检查单独保留，之后的局部成功不会遮住框架失败。
被调用模块或跨包测试来源改变后，相关旧证据不计为当前通过。影响范围包含直接和传递调用及后台任务；仅按当前声明判断，历史删除和系统外调用仍需人工确认。
重要确认样例在原规则表给编号，用 pytest `rule_case` 标记对应实际测试；各数据库、源码版本、测试结果与整轮检查分别显示。规则标注、样例声明或历史通过都不代表业务已验收。

## 固定结构与运行细节

新包由 `tools.new_module` 生成。默认服务与 worker 启动前检查登记、`module.json`、固定文件位置、
步骤函数位置、依赖方向和框架摘要；误建业务目录、越过模块公开入口或无意修改框架会拒绝启动。
步骤和存储文件可按用途增加，包根只接受固定文件与 `data_主题.py`。这限制意外偏离，开发者的文件权限仍由工作环境管理。

计算图直接显示文件、函数、规则与读写字段。实际执行图进一步显示条件判断的结果与耗时、每步耗时与产出，
下层模块、SQL、外部接口与模型调用的时间；SQL 定位到存储函数和调用行，列出表或视图、行数和失败状态。
运行页面与中文报告提供相同细节。大段计算需要更细时间时拆成有意义的步骤，函数内时间包含在所属步骤中。
SQL 每步骤保留前 200 次细节，超出后继续统计次数和总耗时，图中明确标出省略数量；不保存 SQL 参数或查询结果。
旧项目升级后先运行 `tools.adopt_modules`，结构不合格时先调整文件，再检查和启动。

## 已有产品接收模板更新

准备产品上次采用的旧模板和准备升级的新模板，在产品的 `server/` 下运行：

```bash
uv run python -m tools.update_framework --base /旧模板目录 --source /新模板目录
uv run python -m tools.update_framework --base /旧模板目录 --source /新模板目录 --apply
```

默认只预览；文本独立改动可合并，有冲突时全部保留原样。产品业务、登记、依赖、配置与数据库迁移历史
不自动覆盖，相关上游变化另列出。新产品保存 `template-source.json` 记录来源；
旧产品没有共同 Git 祖先也可使用。首次接入、版本不兼容与检查步骤见 [更新说明](server/tools/template/UPGRADING.md)。

## 持续集成

[.github/workflows/check.yml](.github/workflows/check.yml) 在推送到 main、每个合并请求和手动触发时运行两项检查：

| 检查 | 内容 |
| --- | --- |
| 代码与测试 | 在真实的 PostgreSQL 17、Redis、S3 服务 上运行 `tools.check`：代码风格、格式、类型、生成文档是否过期、SQLite 与 PostgreSQL 两轮测试 |
| 部署镜像与配置 | 构建 `server/deploy/Dockerfile`，确认镜像中的接口和 worker 能导入，校验 `compose.yaml` 能否展开 |

依赖严格按 `server/uv.lock` 安装，锁文件与 `pyproject.toml` 不一致时直接失败。第三方 Action 按提交号锁定；[.github/dependabot.yml](.github/dependabot.yml) 每周一检查 Action 和 Python 依赖的新版本：小版本和补丁按类别合并成一个合并请求，大版本各自单独提交，检查通过后再合并。框架文件摘要对 `pyproject.toml` 只锁定 `[tool]` 下的检查配置，依赖更新不需要改摘要。用本模板建立的新仓库会带上同样的检查。

## 这个模板提供什么

| 能力 | 在哪里 |
| --- | --- |
| 模块统一登记，模块之间只通过操作约定调用，依赖方向自动检查 | `server/app/setup/catalog.py`、`server/shared/modules` |
| 流程由步骤组成，步骤声明读写的字段；启动时检查声明，运行时限制越界读写 | `server/shared/flow` |
| 四种图：模块关系、计算流程、字段来源、实际执行 | `server/shared/graphs`、`/api/system/*` |
| 每次执行的运行记录和中文摘要、排查报告 | `server/shared/records`、`tools.diagnose` |
| 事务按步骤声明安排：只读步骤不能写库，失败整体回滚；先读后写用带条件修改或加锁读取 | `server/shared/db` |
| 数据变更历史（谁在哪次运行把哪个字段从什么改成什么）；按位置续读的分页 | `server/shared/db`、`/api/system/changes` |
| 后台任务和定时计划（任务表兼作队列，无需 RabbitMQ） | `server/shared/jobs` |
| 大模型调用入口：提示词版本、用量记录、并发和重试（OpenAI 兼容接口） | `server/shared/model_calls` |
| 外部接口调用：声明外部系统、超时与重试、连续失败后暂停调用、写入结果待确认、调用概要记录 | `server/shared/remote_calls` |
| 导入导出：CSV、Excel 读写，逐行报告问题 | `server/shared/exchange` |
| 缓存（进程内或 Redis）、文件存储（本地目录或 S3 兼容）、流式输出（SSE） | `server/shared/cache`、`files`、`flow` |
| 旧系统迁移：旧库只读入口和迁移步骤 | `server/legacy` |
| 统一错误格式、服务密钥、请求与登录限流、安全响应头、操作记录、结构化日志 | `server/app/api`、`server/shared/access` |
| 用户、角色、组织：登录、刷新令牌轮换、修改密码、管理员发放重置码找回密码、两步验证（TOTP）；数据按组织隔离，也可按负责人隔离（行级权限），漏写条件直接报错；敏感字段加密保存 | `server/service/user_access`、`server/shared/db/org.py`、`owner.py`、`server/shared/access/vault.py` |
| 文件管理：上传、下载、删除和每日清理 | `server/service/file_library` |
| 运行统计、OpenTelemetry 调用过程导出、只读排查网页 | `/api/system/stats`、`server/shared/telemetry`、`/system/console` |
| 质量检查：注释、命名、长度、依赖、README、业务文档，纳入默认测试 | `server/tools/quality` |
| 开发进度与检查：测试失败时附运行报告；生成待确认问题、规则的测试标注、任务数与接口描述；改动影响报告可手动运行，尚未加入持续集成 | `doc/progress.md`、`doc/tasks.md`、`doc/api/`、`server/tools/impact.py` |
| 新模块生成命令、模块独立检查、框架文件摘要、运行查看与任务处理命令 | `server/tools` |
| Docker 镜像、单机部署组合配置、环境检查、备份恢复 | `server/deploy` |
