# 任务状态检查

`uv run dev verify-model` 是独立的小范围检查，不增加服务器依赖，也不加入每次改包的默认检查。

## 检查哪些规则

检查范围是两个后台执行进程（worker）领取同一个 `repeat_safe=True` 普通任务，最多执行两次：只有当前有效的执行尝试可以提交，最终提交最多发生一次。模型把领取、占用超时后接管和最终提交分别视为不可拆分的数据库操作；时间只区分是否达到接管条件，不逐秒枚举。

| 模型动作 | 对应实现 |
| --- | --- |
| claim | `jobs/constraints.take` 在领取事务内按条件更新任务，并递增尝试编号 |
| lease expired and reclaimed | `JobQueue.reclaim` 锁定占用已超时且状态为 running 的任务行，在同一事务调用 `expiry.expire` 重新排队 |
| commit | `Worker.run_job` 的 finish 回调调用 `JobQueue.finish`，业务写入、任务完成标记和 `flow/commit.commit_writes` 提交都在同一事务内；旧尝试抛错后回滚 |

状态模型在 `scripts/fastapi_check/job_model.py`，代码对应表在 `assets/job_model.json`。对应函数变化会让命令失败；先核对模型的前提与状态变化，更新真实回归测试，最后更新该函数源码的 SHA-256 摘要。不能仅更新源码摘要让检查通过。

检查器必须能找到移除尝试编号校验后的反例。实际回归 `tests/framework/test_job_commit.py` 先让旧的执行尝试通过启动前检查，再安排另一个 worker 接管；确认旧尝试确实执行到 finish 时被拒绝、业务写入回滚，新的执行尝试仍保持运行。

模型只检查上述范围。分段任务、资源或串行任务的占用有效期、外部系统实际执行的动作、网络故障和无限次重试需要另外验证；Python/SQL 实现与模型也尚未做完整的等价证明。数据库并发行为由独立 PostgreSQL 测试验证，规则变化时只扩展相关检查。
