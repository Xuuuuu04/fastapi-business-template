# FastAPI 通用后端模板

一个没有预置业务模块的单体后端模板：业务包的结构、声明的写法和事务的安排都是固定的，每次运行的过程和错误都会被记录下来。

- 项目入口：[AGENTS.md](AGENTS.md)
- 使用、开发与迁移方法：[模板使用 Skill](.agents/skills/fastapi-guide/SKILL.md)
- 产品业务与生成文档：[doc/](doc/README.md)
- 服务配置与启动：[server/](server/README.md)
- 版本变化：[CHANGELOG.md](CHANGELOG.md)

项目 Skill 放在 `.agents/skills/`，脚本、参考说明和代码模板跟着对应的 Skill 走。用这个模板创建产品时，会复制这些 Skill；本机的任务、环境、数据库和检查历史不会被复制。
