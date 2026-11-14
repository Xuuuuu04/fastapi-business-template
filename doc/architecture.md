# 架构与模块开发概览

这份说明面向在本项目或下游产品中开发后端功能的工程师与 AI 协作者，概括目录分工、模块结构与核心声明方式。完整的装饰器参数、存储方法和后台任务细节见 [框架用法](../.agents/skills/fastapi-module/references/framework.md)。

## 目录分工

| 路径 | 职责 | 修改约定 |
| --- | --- | --- |
| `server/service/` | 产品业务包（能力包 `capability` 与流程包 `workflow`） | 用 `uv run dev new-module` 生成并在包内迭代 |
| `server/library/` | 无状态纯工具包（不连库、不发外部请求） | 用 `uv run dev new-library` 生成 |
| `server/app/api/v1/` | HTTP 路由层，只做参数接收并调用 `await run(操作, 输入)` | 生成命令自动创建并登记到 `routers.py` |
| `server/app/product.py` | 产品名称、外部服务适配器、模型配置与时钟入口 | 产品按实际环境配置 |
| `server/migrations/` | Alembic 数据库迁移脚本，只允许修改已登记表 | 新增或调整表结构后生成并审查 |
| `server/shared/`、`server/devtools/` | 核心执行器、存储校验、任务队列与开发命令行 | 受框架清单保护，常规业务开发不修改 |
| `doc/api/openapi.json` | 从代码契约自动导出的唯一 OpenAPI 接口文档 | 运行 `uv run dev docs` 更新，供前端对照 |

## 一个业务包里有什么

使用 `uv run dev new-module customer_quote --title 客户报价` 创建能力包后，包内按固定职责拆分文件：

- `public.py`：对外公开的 `contract` 操作声明、输入输出类型与业务错误，是其他包唯一允许导入的入口。
- `data.py`：使用 `Data` 定义不可变输入输出，使用 `WorkData` 定义单次流程的工作数据；每个字段都通过 `meaning()` 写明用途、单位和空值含义。
- `steps/` 与 `calc/`：`@step` 声明步骤名称、读取字段（`reads`）、写入字段（`writes`）及所需能力（`store`、`call`、`later`、`remote`、`effects`、`model`）；复杂纯计算拆入 `calc/` 便于独立单测。
- `flow.py`：用 `Flow` 把步骤串联成完整操作（单条流程不超过 12 步）。
- `store/`：仅能力包拥有，`tables.py` 定义表结构（带 `org_column()`、`owner_column()`、`UtcTime()`、`ExactNumber()`），`contract.py` 声明存储协议，`sql.py` 用 SQLAlchemy Core 实现读写。
- `module.py`：用 `Module` 汇总本包提供的操作、数据表、跨包只读依赖、后台任务计划（`JobPlan`）、定时计划（`Schedule`）与多阶段流程（`Pipeline`）。

## 前后端协作约定

与配套前端模板 [vue3-business-template](https://github.com/mumuxsy/vue3-business-template) 对接时：

1. 可用 `uv run dev new-module user_access --title 账号登录 --preset access` 一键生成符合前端默认登录契约（`/api/v1/access/login`）的账号模块与迁移。
2. 每次响应自动携带 `X-Request-ID` 与 `X-Run-ID`，错误响应正文包含固定 `code`、中文 `message`、字段级 `fields` 和 `run_id`，前端开发者工具可直接关联后台运行记录。
3. 修改接口后运行 `uv run dev docs` 更新 `doc/api/openapi.json`，升级或改接口时可用 `uv run dev compare-api` 检查兼容性变化，前端也可直接用 `npm run api` 对照该文件核验字段。
