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

## 按需使用 TLA+

同一个限定范围另外提供 `assets/JobCommit.tla`：`Claim` 对应领取，`Reclaim` 对应数据库中超时重新排队，`Commit` 对应业务写入与任务完成标记一同提交。单纯经过超时时刻不等于数据库已经接管，模型也不把这两件事混为一谈。两个不变量分别检查当前尝试的提交资格，以及最终最多提交一次。

```bash
uv run dev verify-model --jar /绝对路径/tla2tools-1.7.4.jar
```

无参命令仍使用原来的 Python 状态枚举；加 `--jar` 时使用 TLC，再运行同一条真实旧尝试写入回滚测试。两种方式检查同一范围，不增加生产运行依赖，也不纳入每次业务修改的普通检查。

工具需要 Java 11 以上与固定的 `tla2tools.jar` 1.7.4（TLC 2.19）。只使用本地文件，不自动下载。官方地址与 SHA-256 在 `assets/job_tlc_tool.json`，首次准备工具时可以执行：

```bash
curl --fail --location --proto '=https' --tlsv1.2 \
  https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar \
  --output /绝对路径/tla2tools-1.7.4.jar
shasum -a 256 /绝对路径/tla2tools-1.7.4.jar
```

固定摘要为 `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`，命令会再次核对。JAR 保存在项目外。TLC 每个配置最多运行 60 秒、单 worker、堆内存最多 512 MiB；真实回归最多 120 秒，超时或工具不可用都会失败。

`JobCommit.cfg` 要求模型通过，`JobCommitBroken.cfg` 故意移除当前尝试编号检查，必须以 `CurrentAttemptOnly` 不变量产生反例。最短出错顺序是：worker1 领取第一次尝试，任务被超时重新排队，worker2 领取第二次尝试，worker1 用旧编号提交。语法错误、其他不变量失败和没有发现反例都不能当作成功检测。

每轮日志和结果保存在 `server/var/formal/本轮编号/`，命令始终打印位置。`model.log` 是正常搜索结果，`mutation.log` 包含错误模型的状态轨迹，`implementation.log` 是真实回滚测试，`result.json` 区分整轮状态、实现测试状态、搜索状态数量与失败原因。源码对应函数在运行前后都要核对，模型、配置与映射文件检查期间发生变化也会失败。

TLA+ 检查的是上述有限抽象的安全规则，不证明数据库实现与模型等价，也不覆盖进展或公平性、分段任务、资源租约、外部副作用、PostgreSQL 锁行为、手动重试及无限次执行。实际事务和数据库测试仍要保留。
