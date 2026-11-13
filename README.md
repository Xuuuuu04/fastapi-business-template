# FastAPI 通用后端模板

这个单体后端模板没有预置业务。业务包按统一结构组织，框架负责事务、权限和后台任务，并记录每次运行的步骤与错误。

- 开发入口：[AGENTS.md](AGENTS.md)
- 接口说明：[doc/api/openapi.json](doc/api/openapi.json)
- 版本变化：[CHANGELOG.md](CHANGELOG.md)

项目 Skill 放在 `.agents/skills/`，分别说明怎样查业务、写代码、检查测试、发布运行，以及新建或升级产品。各 Skill 的脚本、参考说明和代码模板都放在自己的目录里，创建新产品时会一起复制。
