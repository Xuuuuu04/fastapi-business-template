# 旧系统迁移

需要复用的旧代码暂放此目录，只由业务模块的 `store/` 导入。设置 `APP_LEGACY_DATABASE_URL` 后，存储构造参数 `legacy` 获得只读数据库入口。旧表使用独立的 `legacy_metadata`，不纳入本项目 Alembic 迁移。先在 `doc/模块名/rules.md` 确认新旧结果样例，再逐步切换读写；迁移完成后删除这里的旧代码。
