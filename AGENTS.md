# FastAPI 单体后端模板 5.1.0

## 业务要点

产品在这里写三五条每次改代码都要知道的业务事实：做什么、谁用、最要紧的规则。完整的业务说明见[业务文档](.agents/skills/fastapi-business/business.md)。

## 目录

| 位置 | 放什么 |
| --- | --- |
| `server/service/` | 业务包 |
| `server/library/` | 纯工具包 |
| `server/shared/` | 框架 |
| `server/app/` | HTTP 入口与应用启动代码；代码生成命令会自动把业务包登记到 `app/setup/catalog.py` 的 `MODULES`，把路由登记到 `app/api/routers.py` 的 `MODULE_ROUTERS` |
| `server/app/product.py` | 配置产品名称、外部服务适配器和时钟 |
| `doc/api/openapi.json` | 唯一生成的接口文档，供前端调用对照 |

## 怎么运行

在 `server/` 目录下执行以下安装、初始化和启动命令（已有 `.env` 时会自动跳过复制）：

```bash
uv sync --locked
test -f .env || cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

## 按任务找 Skill

| 要做的事 | Skill |
| --- | --- |
| 了解业务、找代码、业务做完更新业务文档 | [fastapi-business](.agents/skills/fastapi-business/SKILL.md) |
| 写或改业务代码 | [fastapi-module](.agents/skills/fastapi-module/SKILL.md) |
| 检查和测试 | [fastapi-check](.agents/skills/fastapi-check/SKILL.md) |
| 发布上线、查运行、处理后台任务 | [fastapi-operations](.agents/skills/fastapi-operations/SKILL.md) |
| 新建产品、升级框架、迁移旧系统 | [fastapi-template](.agents/skills/fastapi-template/SKILL.md) |

所有开发命令都是 `uv run dev 子命令`，请在 `server/` 目录下执行。

## 日常流程

1. 改完代码后，在调试阶段运行 `uv run dev check --quick --module 包` 快速检查。
2. 用 `uv run dev run 操作名 --input '{...}' --allow-write` 真跑一次操作，核对运行报告。
3. 提交前运行 `uv run dev check --module 包`；修改了框架或公共代码时运行完整 `uv run dev check`。
4. 提交到任务分支并创建 PR，按 PR 模板填写业务规则、验证结果和升级影响；发布框架版本与部署产品分开操作。
5. 一项业务做完并提交后，按 fastapi-business 更新业务文档。

## 长期约定

- 做业务时不修改框架文件（清单在 `server/shared/modules/validation/framework_files.py`）；确实需要修改时，在提交说明里写清用途和影响。业务文档列在 `REGISTRATION` 中，属于产品文件。
- 凭据或权限不够时停下并说明原因，不去找别的凭据。
- 中文说明要写清对象、动作和结果：`meaning()` 说明字段用途及单位，状态和错误说明原因，外部请求直接写“外部请求记录”，不使用自造内部词。程序按错误码和状态值判断，不匹配中文文案。
