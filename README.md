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

1. 在 GitHub 上点“Use this template”建立新仓库，或者复制本仓库。
2. 模板只保留用户权限和文件管理两个通用模块，不需要时在配置中设置 `APP_DISABLED_MODULES=["user_access","file_library"]`；代码和历史数据保留，接口与执行入口一起关闭。
3. 在根目录 `AGENTS.md` 第 1 节写清产品名称、使用者和主要模块。
4. 每个业务模块先运行 `uv run python -m tools.new_module 模块名 --title 中文名` 生成固定目录和测试，再在 `doc/模块名/` 写清真实需求和规则，按 `AGENTS.md` 第 3 节开发。
5. 开发时用 `uv run python -m tools.check --module 模块名` 单独检查；每次完成后运行 `uv run python -m tools.check`；生产使用 PostgreSQL 时加 `--postgres 数据库地址`。

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
