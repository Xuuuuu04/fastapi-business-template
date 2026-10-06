# FastAPI 通用后端模板

无预置业务模块的单体后端模板。固定业务包、声明步骤与事务，记录每次运行的过程和错误。

- 项目入口：[AGENTS.md](AGENTS.md)
- 使用、开发与迁移方法：[模板使用 Skill](.agents/skills/fastapi-guide/SKILL.md)
- 产品业务与生成文档：[doc/](doc/README.md)
- 服务配置与启动：[server/](server/README.md)
- 版本变化：[CHANGELOG.md](CHANGELOG.md)

项目 Skill 位于 `.agents/skills/`，脚本、参考说明和代码模板跟随对应 Skill。采用本模板创建产品时会复制这些 Skill，不复制本机任务、环境、数据库或检查历史。
