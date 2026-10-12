# 后端运行

在本目录安装与启动：

```bash
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

已有 `.env` 不要覆盖。配置项见 [.env.example](.env.example)；部署、环境验证与恢复见 [deploy/](deploy/README.md)。生产使用 PostgreSQL 时，发布前要在真实环境验证应用权限、数据库和恢复过程。

| 目录 | 用途 |
|---|---|
| [app/](app/) | HTTP 接口、模块登记和启动 |
| [service/](service/) | 业务包，结构固定；模板初始为空 |
| [shared/](shared/) | 流程执行、事务、外部能力和运行记录 |
| [tests/](tests/) | 框架、业务、接口和安全检查 |
| [migrations/](migrations/) | 当前产品的数据库迁移历史 |
| [legacy/](legacy/) | 旧系统的表定义和只读访问 |

开发、生成、检查和迁移的方法由[项目 Skill](../.agents/skills/fastapi-guide/SKILL.md) 说明。本目录没有 tools 包；生产服务不会导入项目 Skill。
