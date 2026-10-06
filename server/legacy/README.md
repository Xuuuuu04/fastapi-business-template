# 旧表与只读访问

需要的旧表定义暂放这里，只由业务模块 `store/` 导入。存储参数 `legacy` 通过 `APP_LEGACY_DATABASE_URL` 获得只读入口。旧表使用独立 `legacy_metadata`，不进入本项目 Alembic 迁移。

正确的旧纯计算迁入业务包内部，由正式步骤调用，不放在这里。迁移方法和完整业务样板见 [业务迁移 Skill](../../.agents/skills/fastapi-migration/SKILL.md)。迁移结束后删除不再需要的旧表代码。
