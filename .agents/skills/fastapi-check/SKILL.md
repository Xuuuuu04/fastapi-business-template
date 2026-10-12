---
name: fastapi-check
description: 验证本项目的业务改动时使用：运行代码风格、类型、结构、文档和测试检查，并记录实际检查的范围。
---

# 项目检查

## 选择检查范围

下面的命令在 `server/` 目录执行：

```bash
# 只调试一个包：最快，只检查这个包
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check --quick --module 模块名
# 几个包一起改：一次检查，公共部分只检查一遍
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check --module A --module B
# 按和 origin/main 的差异，自动找出受影响的包
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check --affected --base origin/main
# 完整检查
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check
# 审查完框架改动后，更新框架摘要
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py framework_lock --update
```

怎么选：

- `--quick` 只用于一个包内的调试，它不能证明几个包放在一起也是对的。
- 改动涉及多个包时，用 `--module` 一次列全。
- 改了公共代码，或不确定影响哪里，跑完整检查。
- 整批交付和发布前，跑完整检查。
- 生产使用 PostgreSQL 时加上 `--postgres 测试数据库地址`，只能用已授权的隔离数据库。
- 浏览器、容量、部署是另外的检查，按各自任务单独做，这个命令不包含。

## 业务现状过期

文档检查也会核对 `.agents/records/business-state/模块名.md` 的生成部分：源码或依赖版本、声明发生了变化，生成超过 24 小时，或者摘要与同名 JSON 不一致，都会报错。check 只做比较，不会自动刷新。处理顺序是：先读手写判断并更新下一步，然后显式运行 project business_state；需要真实运行状态时，在确认当前数据库和授权后加 `--runs`，否则保持未知。export_docs 可以初始化或更新过期的声明状态，但不读取数据库，不能代替业务验收。迁移含定时或长流程时，完成条件是先用 operations drill 按真实规模跑通整条链、核对产物和回放覆盖情况，再补局部细节。

## 框架摘要

`server/framework.lock` 记录公共代码、检查配置和项目 Skill 的内容摘要，防止它们被顺手改掉。

- 做业务时不要改这些文件。
- 确实要改，先看实际差异，写明用途和影响，再用 `framework_lock --update` 更新摘要。
- 服务启动只检查运行必需的公共文件，部署时不需要带 Skill。

## 写测试的要求

- 预期结果来自业务文档里确认过的样例。旧系统的输出只能用来比较兼容性，不能当作正确答案。
- 和时间有关的样例：在操作执行时传入时间，或使用可控的时钟。不要在模块导入时就算好有效期，也不要为了让测试通过而放宽业务时限。
- 权限测试使用真实的应用权限。
- 事务、并发、外部操作结果未知、重启后恢复，按这项业务的风险程度来覆盖。

## 检查失败时

先读自动附带的中文运行报告，判断失败属于哪一类：

1. 代码实现有错。
2. 测试本身安排错了。
3. 缺少真实的数据来源。
4. 功能还没做。

当前业务和公共安全问题修复之后，才能说当前目标完成。其他交付条件单独列出来，不要悄悄并入当前阶段。

## 记录

每次检查都记下：代码版本、数据库类型、实际运行的命令和结果。完整检查失败之后，不能用之后一次局部检查的成功去覆盖它。

查询额度在公开的 contract 里声明 QueryBudget；显式声明后，测试超额默认失败，旧的未声明操作只警告。APP_QUERY_BUDGET_MODE=warn 可以临时只警告；逐项迁移完成后改成 error，让默认额度也在测试中报错。生产环境只记录。接入方法和测量含义见 server/shared/db/README.md。

命名检查的来历和删除条件见[检查说明](references/check-rationale.md)；没有当前替代证据时，不因为耗时或以前通过而删除检查。
