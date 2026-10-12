---
name: fastapi-docs
description: 业务代码、字段、接口、规则或计划改变后，生成或检查接口文档和流程文档时使用。
---

# 文档生成

## 哪些手写，哪些生成

| 内容 | 来源 |
|---|---|
| `doc/模块名/needs.md`（需求）、`rules.md`（规则）、`changes.md`（变化记录） | 由人维护 |
| 字段、接口、数据表、流程 | 从代码自动生成 |

开发方法和迁移方法只写在对应的 Skill 里，`doc/` 下不重复。所有生成文字遵循 [文风与术语约定](references/writing-style.md)。

## 命令

在 `server/` 目录执行：

```bash
# 生成文档
uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs
# 只比较声明文档/业务现状，不刷新它们；本机汇总仍会生成
uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs --check
```

随源码提交的生成结果有：`doc/api/`、每个业务包的 `flows.md`，以及 AGENTS.md 的当前状态生成段。

`modules.md`、`development.md`、`progress.md` 三份汇总在导出、检查或查看摘要时生成，已加入 .gitignore，不再提交。已有产品升级时先 `git rm --cached` 这三份（本机文件保留），再执行 export_docs。needs/rules/changes 继续随源码提交。

计划中的实际对应操作在导出时记入 implemented_operations；已实现操作被删除或改名后，检查会指出 project-plan.json 里的具体项，先同步计划再导出。旧的 flows 文档也作为首次迁移的已实现证据。

导出命令会同时初始化或更新过期的 `.agents/records/business-state/模块名.md` 生成部分（同名 JSON 是完整明细），不访问数据库，未知的信息明确标未知；已有的有效运行观察会保留，手写的业务判断、外部依赖和下一步不会被覆盖。最近的运行状态需要在确认数据库和授权后用 project business_state --runs 刷新。生成超过 24 小时，或源码、依赖、声明发生了变化，`--check` 和 fastapi-check 会报错，不会自动刷新。这些记录不提交、也不进入模板副本；开工先读、收工更新。

## 注意

- 生成的文档只描述代码里的声明和计划，不能证明业务已经验收，也不能证明实际跑过。检查结果和运行记录放在本机目录，所以生成文档里不会带旧的检查结果。
- 生成后，检查需要提交的文档和入口生成段有没有差异；汇总不进提交。生成状态里不放人工业务判断，手写部分保持独立。
- 字段含义缺失：去数据模型里补 `meaning()`。规则或样例缺失：去业务文档补。不要手工改生成出来的文件，下次生成会被覆盖。
- 还没有业务包时，生成的业务部分是空的，这是正常的。
