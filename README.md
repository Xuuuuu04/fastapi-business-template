# FastAPI 通用后端模板

面向中小企业单体后端和 AI 业务的项目模板：人审查业务和架构，AI 按固定结构逐个模块开发或迁移旧系统；运行时每次执行都留下可以按编号查询的中文记录，出问题时能直接定位到步骤、字段、规则和源码位置。

## 目录

| 目录 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | AI 开发者的入口：阅读顺序、开发步骤、禁止事项、排查方法 |
| [server/](server/) | 后端代码、测试、迁移、部署 |
| [doc/](doc/) | 业务文档：需求、规则、变化记录，以及自动生成的流程图 |
| [design/](design/) | 模板自身的设计记录；用模板开发产品时可以删除 |

## 快速开始

```bash
cd server
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

打开 http://127.0.0.1:8000/docs 。更多命令见 [server/README.md](server/README.md)。

## 这个模板提供什么

| 能力 | 在哪里 |
| --- | --- |
| 模块统一登记，模块之间只通过操作约定调用，依赖方向自动检查 | `server/app/setup/catalog.py`、`server/shared/modules` |
| 流程由步骤组成，步骤声明读写的字段；启动时检查声明，运行时限制越界读写 | `server/shared/flow` |
| 四种图：模块关系、计算流程、字段来源、实际执行 | `server/shared/graphs`、`/api/system/*` |
| 每次执行的运行记录和中文摘要、诊断报告 | `server/shared/records`、`tools.diagnose` |
| 事务按步骤声明安排：只读步骤不能写库，失败整体回滚 | `server/shared/db` |
| 后台任务和定时计划（任务表兼作队列，无需 RabbitMQ） | `server/shared/jobs` |
| 大模型调用入口：提示词版本、用量记录、并发和重试 | `server/shared/model_calls` |
| 统一错误格式、服务密钥与权限、请求限制、结构化日志 | `server/app/api` |
| 质量检查：注释、命名、长度、依赖、README、业务文档，纳入默认测试 | `server/tools/quality` |
| 新模块生成命令、删除示例命令、框架文件摘要 | `server/tools` |
| Docker 镜像、单机部署组合配置、环境检查、备份恢复 | `server/deploy` |
