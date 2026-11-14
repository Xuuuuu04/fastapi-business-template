# 参与贡献指南

这份指南面向希望改进 `fastapi-business-template` 的开发者与 AI 协作者，说明仓库接收哪些改动、代码与文档需要遵守什么规范，以及提交 Pull Request 前必须跑通哪些检查。

## 贡献范围

本仓库是没有预置业务的通用单体后端模板。提交改动前请先区分框架能力与具体产品业务：

- **适合贡献到本仓库的内容**：`server/shared/`（流程执行器、存储封装、任务队列、多阶段流程、外部调用、权限与加密）、`server/devtools/` 与 `.agents/skills/`（代码生成、静态与架构检查、产品初始化与三方合并升级）、`server/app/api/system/`（运行排查台与系统诊断接口）、`server/deploy/` 部署模板及配套测试与文档。
- **不应放进本仓库的内容**：具体行业的业务表和路由（测试样例统一放在 `server/tests/` 下）。

如果你想先讨论较大的架构改动或新特性，可以先提交 Feature Request Issue 对齐方向再动手。

## 代码与文档规范

仓库通过自动化测试强制执行代码与文风规范，不满足时检查会直接报错：

1. **类型与复杂度**：Python 版本为 `>=3.12,<3.14`，启用严格 `mypy`（禁止未标注函数和裸 `dict`/`list`/`Any`），`ruff` 单函数圈复杂度上限为 10，单行长度不超过 100。
2. **不写普通注释**：代码与前端排查脚本不写解释性注释或文档字符串，用清晰的模块名、函数名、类型、错误类和自动化测试表达意图；字段用途、单位与空值含义统一写在 `Data` / `WorkData` 的 `meaning()` 中。
3. **异步与并发边界**：禁止在异步路径调用同步阻塞 I/O；耗时的纯计算步骤显式标记 `heavy=True`。写事务开始后（即首个 `saves=True` 步骤之后）不能调用大模型或外部接口。
4. **中文表达要求**：所有 Markdown 文档、错误提示、`meaning()` 说明和排查台文案使用直白完整的中文句子，写清对象、动作与结果；不使用中文破折号、直角引号、自造内部黑话或推卸责任的防御性套话（详见 `.agents/skills/fastapi-check/scripts/fastapi_check/quality/docs.py`）。

## 本地开发与验证步骤

所有命令都在 `server/` 目录下运行：

```bash
cd server
uv sync --locked
uv run dev check --delivery
```

根据改动范围补充对应验证：

| 改动内容 | 需要额外运行的检查 |
| --- | --- |
| 存储封装、数据库锁、数值精度或迁移检查 | 配置本地测试 PostgreSQL 后运行 `uv run dev check --postgres postgresql+psycopg://...` |
| 后台任务状态流转、租约续期、取消或重试逻辑 | 运行 `uv run dev verify-model` 核对状态模型与源码映射 |
| 模板初始化（`new-project`）或升级合并（`upgrade`） | 确认 `tests/architecture/test_project_initialization.py` 与 `test_template_updates.py` 全部通过 |
| 系统排查台（`console.html` / `console.js`） | 启动本地服务实际打开 `/system/console` 点检交互与列表展示 |

不要通过删除断言、放宽阈值或在 `rules.py` 添加例外来绕过检查。

## 提交 Pull Request

1. 从 `main` 创建清晰命名的分支，一次提交聚焦一件完整的事，提交说明用朴素中文写明改了什么、为什么改、怎么验证的。
2. 按 [.github/pull_request_template.md](.github/pull_request_template.md) 如实填写改动行为、源码定位、实际执行的验证命令与通过数量，未运行的环境直接写明“未验证”。
3. 如果改动会影响已初始化的下游产品升级（例如修改了 `pyproject.toml`、`server/.env.example` 或框架表结构），请在 PR 的“审查与升级”一栏写明升级步骤与回退办法。
