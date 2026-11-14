# 任务状态检查

`uv run dev verify-model` 是限定范围的状态模型检查，不增加服务运行依赖，也不放进每次修改业务包时运行的常规检查。

## 检查范围与代码映射

检查范围为两个后台 worker 并发领取同一个 `repeat_safe=True` 普通任务、最多执行两次：只有持有效尝试编号的 worker 才能提交，最终提交最多发生一次。领取、超时接管和最终提交分别视为原子数据库操作；时间只区分是否到达超时接管条件。

| 模型动作 | 对应实现 |
| --- | --- |
| `claim` | `jobs/constraints.take` 在领取事务内按条件更新任务并递增尝试编号 |
| `lease expired and reclaimed` | `JobQueue.reclaim` 锁定已超时的 `running` 任务行，在同一事务调用 `expiry.expire` 重新排队 |
| `commit` | `Worker.run_job` 的收尾回调调用 `JobQueue.finish`，将业务写入与任务完成标记在同一事务提交；旧尝试提交时抛错并回滚 |

状态模型写在 `scripts/fastapi_check/job_model.py`，代码摘要映射在 `assets/job_model.json`。改动这几个关键函数前，先核对模型前提和状态转换，同步更新 `tests/framework/test_job_commit.py` 真实回滚回归测试，最后再更新 `job_model.json` 中的源码 SHA-256。检查器同时会验证“故意移除尝试编号校验”的反例能否被抓出。

## 按需使用 TLA+

同一个限定范围另配有 `assets/JobCommit.tla`：`Claim` 对应领取，`Reclaim` 对应超时接管重新排队，`Commit` 对应写入与完成标记一并提交。超时时刻到达后，要等 `Reclaim` 更新数据库状态才算完成接管。

```bash
uv run dev verify-model --jar /绝对路径/tla2tools-1.7.4.jar
```

无参数时运行 Python 状态枚举和真实回滚测试；加 `--jar` 时额外运行本地 TLC（需 Java 11+ 和固定的 `tla2tools.jar` 1.7.4，SHA-256 见 `assets/job_tlc_tool.json`）。`JobCommit.cfg` 检查正常不变量，`JobCommitBroken.cfg` 检查故意去掉尝试编号后的反例，两种结果分别写进 `server/var/formal/本轮编号/` 下的 `model.log`、`mutation.log`、`implementation.log` 和 `result.json`。

分段任务、资源占用有效期、外部请求、无限重试与 PostgreSQL 数据库行锁仍由各自的框架单元测试与 PostgreSQL 并发测试分别验证。
