# 数据库迁移

001_notes.sql 建立初版笔记表，以 SQLite user_version 记录版本 1。通过 uv run python -m shared.db.migrate 执行。

重复执行不删除数据；高于当前版本的数据库拒绝处理。当前只有初始迁移，没有通用增量迁移或数据库降级实现。后续表结构变化必须增加新的版本处理，不能修改已经应用的 SQL。
