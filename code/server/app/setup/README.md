# 后端组装

app.py 创建 FastAPI，登记路由和公共处理；build.py 按请求构造 NoteService 与 SQLite 存储；life.py 设置运行日志。

应用创建不连接数据库，不自动迁移。每次数据库请求结束关闭自己的连接。当前只有一个 Web 单体进程，没有后台执行器。
