---
name: fastapi-docs
description: 业务代码、字段、接口、规则或计划改变后，生成或检查接口文档和流程文档时使用。
---

# 文档生成

## 哪些手写，哪些生成

| 内容 | 来源 |
|---|---|
| `doc/模块名/needs.md`（需求）、`rules.md`（规则）、`changes.md`（变化记录） | 产品手写维护 |
| 字段、接口、数据表、流程 | 从代码自动生成 |

开发方法和迁移方法只写在对应的 Skill 里，`doc/` 里不重复。

## 命令

在 `server/` 执行：

```bash
# 生成文档
uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs
# 只检查已生成的文档是否和当前代码一致，不写文件
uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs --check
```

提交的生成结果：`doc/api/`、每个业务包的 `flows.md`，以及AGENTS.md的当前状态生成段。

`modules.md`、`development.md`、`progress.md`在导出、检查或查看摘要时生成，加入.gitignore，不再提交。已有产品升级时先git rm --cached这三份（保留本机文件），再执行export_docs。needs/rules/changes继续随源码提交。

计划中的实际对应操作在导出时记入implemented_operations；已实现操作删除或改名后，检查指出project-plan.json的具体项，先同步计划再导出。旧flows文档也作为首次迁移的已实现证据。

## 注意

- 生成的文档只描述代码里的声明和计划，不能证明业务已经验收，也不能证明实际跑过。检查结果和运行记录放在本机目录，所以生成文档里不会带旧的检查结果。
- 生成后检查需提交文档及入口生成段差异；汇总不进提交。生成状态不放人工业务判断，手写部分保持独立。
- 字段含义缺失：去数据模型里补 `meaning()`。规则或样例缺失：去业务文档补。不要手工改生成出来的文件，下次生成会被覆盖。
- 还没有业务包时，生成的业务部分是空的，这是正常的。
