---
name: fastapi-check
description: 验证本项目局部业务、共同版本或整批交付时使用，执行代码风格、类型、结构、文档及测试并记录实际范围。
---

# 项目检查

按当前业务与共同影响选择范围。以下命令在 `server/` 执行：

```bash
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check --quick --module 模块名
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check --module A --module B
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check --affected --base origin/main
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py check
uv run python ../.agents/skills/fastapi-check/scripts/run_check.py framework_lock --update
```

快速检查只用于包内调试，不代替共同版本检查。多个受影响包一次检查，公共检查只做一次。公共或未知变化需要完整检查；整批交付和发布前完整检查。生产使用 PostgreSQL 时加 `--postgres 测试数据库地址`，测试只用授权的隔离库。浏览器、容量和部署按实际任务另行检查。

框架摘要保护公共代码、检查配置和项目 Skill；业务开发不顺手改它们。确需修改时检查真实差异、说明用途和影响，再更新摘要。服务启动只检查运行所需的公共文件，不要求部署 Agent Skill。

测试预期来自确认业务样例；旧输出只证明兼容比较。时间敏感样例在操作时设置时间或用受控时钟，不在模块导入时计算有效期，不放宽业务时限来通过测试。权限检查使用真实应用权限；事务、并发、外部动作未知结果与重启恢复按当前业务风险覆盖。

失败先看中文运行报告，分清实现错误、测试安排错误、缺少真实来源与尚未实现功能。当前业务及公共安全错误修复后才能算当前目标完成；其他交付条件另列，不偷偷扩大当前阶段。记录源码版本、数据库类型、实际命令与结果；完整失败不能被后来局部成功覆盖。
