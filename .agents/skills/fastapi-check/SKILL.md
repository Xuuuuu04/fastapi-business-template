---
name: fastapi-check
description: 验证改动时使用：跑静态检查（风格、格式、类型、接口文档）和相关测试。
---

# 项目检查

`uv run dev check` 只做两件事：静态检查和跑测试。不复制项目、不存档、不沿用上次结果，每次都真跑。在 `server/` 执行：

```bash
# 调试一个包：只查这个包的风格、格式和测试
uv run dev check --quick --module 模块名
# 改了几个包：静态检查跑一次，测试只跑这几个包
uv run dev check --module A --module B
# 按和 origin/main 的差异自动选受影响的包
uv run dev check --affected --base origin/main
# 全部检查；--group 可以只跑 pure、module、flow 或 framework 一组测试
uv run dev check
# 交付检查：额外要求没有模拟步骤
uv run dev check --delivery
# 测试改用隔离的 PostgreSQL（只能用已授权的测试库）
uv run dev check --postgres 测试数据库地址
```

- 先用最小范围：调试用 `--quick --module`，改了公共代码再跑全部。
- 默认用 SQLite；生产用 PostgreSQL 的，发布前加 `--postgres` 跑一次。
- 浏览器、容量、部署是另外的检查，这个命令不包含。

## 框架文件

`shared/modules/validation/framework_files.py` 列出哪些是框架文件（公共代码、检查配置和项目 Skill）。

- 做业务时不要改这些文件。
- 确实要改，在提交说明里写明用途和影响，靠代码审查把关。

## 写测试的要求

- 预期结果来自和用户确认过的业务样例。旧系统的输出只能用来比较兼容性，不能当作正确答案。
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

查询额度在公开的 contract 里声明 QueryBudget；显式声明后，测试超额默认失败，旧的未声明操作只警告。APP_QUERY_BUDGET_MODE=warn 可以临时只警告；逐项迁移完成后改成 error，让默认额度也在测试中报错。生产环境只记录。接入方法和测量含义见 server/shared/db/README.md。

命名检查的来历和删除条件见[检查说明](references/check-rationale.md)；没有当前替代证据时，不因为耗时或以前通过而删除检查。
