---
name: fastapi-check
description: 验证本项目的业务改动时使用：运行代码风格、类型、结构、文档和测试检查，并记录实际检查的范围。
---

# 项目检查

## 选择检查范围

下面的命令在 `server/` 执行：

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

- `--quick` 只用于一个包内的调试，不能证明几个包放在一起是对的。
- 改动涉及多个包，用 `--module` 一次列全。
- 改了公共代码，或不确定影响哪里，跑完整检查。
- 整批交付和发布前，跑完整检查。
- 生产用 PostgreSQL 时加 `--postgres 测试数据库地址`。只能用已授权的隔离数据库。
- 浏览器、容量、部署另按任务单独检查，这个命令不包含。

## 框架摘要

`server/framework.lock` 记录公共代码、检查配置和项目 Skill 的内容摘要，防止它们被顺手改掉。

- 做业务时不要改这些文件。
- 确实要改，先看实际差异，写明用途和影响，再用 `framework_lock --update` 更新摘要。
- 服务启动只检查运行必需的公共文件，部署时不需要带 Skill。

## 写测试的要求

- 预期结果来自业务文档里确认过的样例。旧系统的输出只能用来比较兼容性，不能当作正确答案。
- 和时间有关的样例：在操作执行时传入时间，或使用可控的时钟。不要在模块导入时就算好有效期，也不要为了让测试通过放宽业务时限。
- 权限测试使用真实的应用权限。
- 事务、并发、外部操作结果未知、重启后恢复，按这项业务的风险程度覆盖。

## 检查失败时

先读自动附带的中文运行报告，判断属于哪一类：

1. 代码实现有错。
2. 测试本身安排错了。
3. 缺少真实的数据来源。
4. 功能还没做。

当前业务和公共安全问题修复后，才能说当前目标完成。其他交付条件单独列出，不要悄悄并入当前阶段。

## 记录

每次检查记下：代码版本、数据库类型、实际运行的命令和结果。完整检查失败后，不能用之后一次局部检查的成功去覆盖它。
