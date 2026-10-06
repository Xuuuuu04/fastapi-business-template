---
name: fastapi-module
description: 在本 FastAPI 项目新增业务模块或把已有模块改成固定结构时使用，包含生成器与模块代码模板。
---

# 业务模块开发

先在 `doc/模块名/needs.md` 和 `rules.md` 写当前业务用途、明确规则与确认样例。未定业务含义标待确认。生成命令在 `server/` 执行：

```bash
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_module customer_contact --title 客户联系人
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py adopt_modules
```

生成器建立固定业务包、测试、业务文档、HTTP 入口，并更新公共登记。不要复制一个已有业务包当作新包。`adopt_modules` 只在旧包全部满足结构检查后写入结构说明，不改业务实现。

计算在 `steps/`，数据库与外部动作在 `store/`；流程在 `flow.py` 声明，输入、工作数据与返回模型在 `data.py`，跨包只导入 `public.py`。字段用 `meaning()` 解释含义，步骤声明读写字段与规则编号。具体目录见 `server/service/README.md`，步骤与事务见 `server/shared/flow/README.md`。

完成一项业务所需的包及时在同一版本运行。新表先升级隔离库到现有 head，再生成并人工检查增量迁移；既有数据库历史不替换。局部调试用检查 Skill 的 `--quick --module`，共同版本用明确的多个受影响包，整批交付完整检查。文档生成只做一次。

旧系统业务另读 `fastapi-migration`。模板资产位于 [assets/templates](assets/templates/)，生成器直接使用这些资产。
