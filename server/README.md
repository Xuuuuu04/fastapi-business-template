# 后端运行

在本目录安装与启动：

```bash
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

已有 `.env` 不覆盖。配置项见 [.env.example](.env.example)，部署、环境验证与恢复见 [deploy/](deploy/README.md)。生产使用 PostgreSQL 时，发布前验证真实应用权限、数据库和恢复过程。

| 目录 | 用途 |
|---|---|
| [app/](app/) | HTTP、登记与启动 |
| [service/](service/) | 固定业务包，模板初始为空 |
| [shared/](shared/) | 执行、事务、外部能力与运行记录 |
| [tests/](tests/) | 框架、业务、接口和安全检查 |
| [migrations/](migrations/) | 当前产品数据库历史 |
| [legacy/](legacy/) | 独立旧表定义与只读访问 |

开发、生成、检查和迁移命令分别由 [项目 Skill](../.agents/skills/fastapi-guide/SKILL.md) 说明。本目录没有 tools 包。生产服务不导入项目 Skill。
