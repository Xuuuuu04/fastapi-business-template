# 数据库

当前使用 Python 标准库 SQLite。connect.py 管理连接和就绪检查，migrate.py 显式执行迁移，migrations/001_notes.sql 建立笔记表。

每个请求一个连接，业务事务负责提交或回滚，请求结束关闭连接。初始化使用 uv run python -m shared.db.migrate，不在服务启动时自动建表。

默认文件为 var/app.db，仅验证本地使用。尚未提供 PostgreSQL、连接池和生产迁移工具。
