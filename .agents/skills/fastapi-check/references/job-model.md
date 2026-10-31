# 任务状态模型

`uv run dev verify-model` 是独立的小范围检查，不增加服务器依赖，也不加入每次改包的默认检查。

## 检查的性质

两个 worker 竞争一个 `repeat_safe=True` 的普通任务，最多两次尝试：只有当前尝试可以提交，至多一次最终提交。领取、租约到期后的接管、最终提交作为数据库原子转移；时间只抽象为已符合接管条件，不穷举秒数。

| 模型动作 | 实现边界 |
| --- | --- |
| claim | `jobs/constraints.take` 中条件更新和尝试编号递增，位于领取事务内 |
| lease expired and reclaimed | `JobQueue.reclaim` 锁定已过期且 running 的行，在同一事务调用 `expiry.expire` 重新排队 |
| commit | `Worker.run_job` 的 finish 回调调用 `JobQueue.finish`，业务写入、任务完成和 `flow/commit.commit_writes` 提交在同一事务；旧尝试抛错后回滚 |

状态模型在 `scripts/fastapi_check/job_model.py`，代码对应表在 `assets/job_model.json`。对应函数变化会让命令失败；先审查模型假设、更新状态转移及实际回归，再更新该函数源码 SHA-256。不能只更新摘要消除失败。

检查器必须能找到移除尝试编号校验后的反例。实际回归 `tests/framework/test_job_commit.py` 让旧尝试通过执行前检查，再安排接管，确认它确实执行到 finish、业务写入回滚、新尝试保持运行；不是仅在入口拒绝旧任务。

这个有界模型不包含分段任务、资源/串行租约、外部系统副作用、网络故障或无限次数重试，也不证明 Python/SQL 实现完全等价于模型。生产数据库并发语义由独立 PostgreSQL 测试验证。规则变复杂时只扩大相关模型，不引入通用形式化平台。
