# FastAPI 通用后端模板

一个没有预置业务的单体后端模板：业务包的结构、声明的写法和事务的安排都只有一种，每次运行的过程和错误都会记录下来。

- 开发入口：[AGENTS.md](AGENTS.md)
- 接口契约：[doc/api/openapi.json](doc/api/openapi.json)
- 版本变化：[CHANGELOG.md](CHANGELOG.md)

项目 Skill 在 `.agents/skills/`，每个 Skill 的脚本、参考说明和代码模板放在它自己的目录里。用这个模板创建产品时会复制这些 Skill。
