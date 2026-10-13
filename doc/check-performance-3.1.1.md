# 3.1.1 模板检查实测

2026-10-13，在模板工作树的 `server/` 执行。数据库为已授权的本机隔离 PostgreSQL 控制库；连接地址和密码不写入本文。所有测试原有断言、200 成员规模、超时阈值与完整交付范围保持不变，没有新增跳过条件。

## 最终结果

| 命令 | 修改前本机实测 | 最终实测 | 结果 |
| --- | ---: | ---: | --- |
| `uv run dev check --database sqlite --delivery` | 89.092 秒 | 58.714 秒 | 824 通过，15 个原有条件跳过 |
| `uv run dev check --database both --postgres <隔离控制地址> --delivery` | 266.552 秒 | 253.705 秒 | SQLite 824 通过，PostgreSQL 834 通过；原有条件跳过分别 15、5 |

实际运行通过 `/Users/mumuxsy/.local/bin/uv run --offline` 启动，内部检查命令相同。SQLite 达到约 60 秒目标，双库没有达到约 180 秒目标；本次实测降幅分别为 34.1% 和 4.8%。用户之前的 115 秒、约 7 分钟是另一次环境下的历史记录，不作为本工作树的实测基线。

SQLite 初轮类型检查为 7.632 秒，末轮为 0.685 秒，其中一部分收益来自正常增量缓存变热；双库基线与末轮的类型检查分别为 0.380、0.346 秒。不能把冷、热缓存差异全归功于调度。

最终记录（本机资料，不提交）：

- SQLite：`server/var/development/checks/5917e55bb8004be19cd44a67bcec6b90.json`。
- 双库：`server/var/development/checks/9d0ca900206e42ab962eaaa60339c541.json`。
- 完整日志：`server/var/final-sqlite.log`、`server/var/final-both.log`。
- 子进程计时：`server/var/subprocess-timing.jsonl`、`server/var/pg-subprocess-timing.jsonl`。

## 慢在哪里

使用完整交付命令自带的 `--durations=10`，另以真实 `subprocess.run` 的单调时钟逐步计时；不是用模拟命令估算。

| 测试 | 子步骤实测 | 结论 |
| --- | --- | --- |
| `test_tools.py::test_new_project_path` | 修改前模块检查 12.199 秒，副本完整 pytest 26.489 秒；复制、生成、迁移与文档等各步小于 2 秒 | 主要是冷类型检查与完整副本测试；保留副本完整 pytest，只让小范围模块检查串行并复用类型缓存 |
| `test_skeleton_generator.py::test_three_package_skeleton_to_real_with_error_position` | 修改前 finish 11.538 秒，拒绝模拟包的交付检查 6.214 秒；三次实际样例 pytest 各约 1.6 至 1.8 秒 | 多次冷公共检查，而非真实等待；缓存复制后 finish 为 6.531 秒，拒绝交付为 5.249 秒 |
| `test_operation_generators.py::test_new_operation_and_pipeline_check_without_manual_edits` | 修改前模块检查 11.035 秒；类型缓存复制后 7.242 秒 | 主要是公共类型检查；复制及生成不是关键路径，副本小范围检查不再额外创建 worker |
| `test_integration_cli.py::test_real_two_package_merge_and_dual_database_evidence` | 最终单独实测整合命令 88.477 秒，其中完整双库检查 76.303 秒：类型 5.619 秒、SQLite 44.053 秒、PostgreSQL 69.171 秒 | 真正的完整双库子进程是主要耗时；迁移验证和整合刷新约占其余 12 秒，没有缩小完整范围 |
| `test_task_cli.py::test_real_task_commands_use_fresh_database_evidence` | 最终单独实测拒绝模拟实现的 finish 5.897 秒，真实双库 finish 7.783 秒；后者双库测试为 1.827、2.724 秒，类型为 0.428 秒 | 多次真实收工和公共检查，不是安装依赖或真实 sleep；缓存变热后类型分析成本下降 |
| `test_fanout.py::test_200_members_wait_join_and_frozen_sources` | 基线 SQLite 21.40 秒，双库轮 PostgreSQL 54.17 秒；最终分别为 26.34、58.54 秒 | 200 成员真实事务、队列和运行记录成本；受控时钟已经消除业务等待，没有降低成员数或等待阈值 |

这些套娃测试本来就使用当前解释器和已安装依赖，没有重复 `uv sync`。唯一真实离线安装是生产安装验收测试，继续保留。整合和任务两项最终单独计时共 2 个测试，全部通过，分别为 94.15、23.09 秒。

## 最终 SQLite 最慢 10 项

| 秒 | 测试（位于 `server/tests/`） |
| ---: | --- |
| 51.60 | `architecture/test_tools.py::test_new_project_path` |
| 32.56 | `architecture/test_skeleton_generator.py::test_three_package_skeleton_to_real_with_error_position` |
| 26.34 | `framework/test_fanout.py::test_200_members_wait_join_and_frozen_sources` |
| 16.43 | `architecture/test_operation_generators.py::test_new_operation_and_pipeline_check_without_manual_edits` |
| 2.87 | `framework/test_fanout.py::test_retry_only_failed_member` |
| 2.86 | `architecture/test_project_summary.py::test_real_cli_keeps_old_json_and_does_not_open_database` |
| 2.60 | `framework/test_pipeline_drill.py::test_100000_rows_original_replay` |
| 2.41 | `framework/test_fanout.py::test_ratio_seals_accepted_results` |
| 2.31 | `architecture/test_skill_lifecycle.py::test_copy_retains_skills_and_uses_product_paths` |
| 2.15 | `architecture/test_skill_lifecycle.py::test_server_starts_without_project_skills` |

## 最终双库轮 PostgreSQL 最慢 10 项

| 秒 | 测试（位于 `server/tests/`） |
| ---: | --- |
| 143.18 | `architecture/test_integration_cli.py::test_real_two_package_merge_and_dual_database_evidence` |
| 88.92 | `architecture/test_tools.py::test_new_project_path` |
| 58.54 | `framework/test_fanout.py::test_200_members_wait_join_and_frozen_sources` |
| 34.77 | `architecture/test_upgrade_acceptance.py::test_real_v2_product_upgrade_and_incremental_databases` |
| 31.74 | `architecture/test_task_cli.py::test_real_task_commands_use_fresh_database_evidence` |
| 28.61 | `architecture/test_skeleton_generator.py::test_three_package_skeleton_to_real_with_error_position` |
| 13.18 | `architecture/test_operation_generators.py::test_new_operation_and_pipeline_check_without_manual_edits` |
| 5.55 | `framework/test_segmented_jobs.py::test_100000_rows_resume_after_sigkill` |
| 3.52 | `architecture/test_migration_validation.py::test_real_dual_database_incremental_migration` |
| 3.43 | `framework/test_pipeline_drill.py::test_100000_rows_original_replay` |

同轮 SQLite 的前四项为新项目 87.51 秒、骨架 58.32 秒、200 成员 30.87 秒、操作生成器 27.13 秒；其余为失败重试 5.44 秒、组织隔离 3.96 秒、十万行回放 3.72 秒、比例汇合 2.96 秒、项目摘要 2.51 秒、备份版本 2.37 秒。两库 pytest 分别耗时 158.87、250.92 秒；包括启动和公共检查后的整轮为 253.705 秒。

## 采用与撤回

- 每份生成项目仍有独立源码、文档和数据库，依赖继续使用当前已安装环境；仅复制 `.mypy_cache`，由 mypy 自行核对源码、选项和依赖。新样例证明修改副本缓存不影响来源、修改类型后仍真实失败。
- 使用 load 调度和小批次，长短样例交替，先分配长任务；新样例证明测试对象和数量不变。副本小范围检查显式串行，完整副本 pytest 仍为两进程；整合仍执行完整双库检查。
- 自动预算为 CPU 数量减二、至少二个、最多四个；程序化默认零不变。默认预算八时 SQLite 曾为 64.081 秒，六时为 69.788 秒；两库用 1/3 分配时 SQLite 反而约 209 秒，因此四预算时保留 2/2，手动至少六预算才让 PostgreSQL 使用约三分之二。每库实际 worker 数和总预算写入证据。
- 试过全局和同库系统文件锁，让 200 成员样例之间排队；全局锁出现 178 秒等锁，同库锁单库为 77.131 秒，整合出现原有 240 秒超时。没有放宽阈值，实验全部撤回，没有留下锁或新跳过条件。
- 中间版本双库曾为约 209 秒，但最后源码的结果是 253.705 秒，不能把中间结果冒充最终验收。

## 按包沿用结果

暂不实现。现有操作覆盖汇总属于单轮，不能证明多轮局部证据覆盖了同一版本的整个目录；共享框架、依赖与测试环境变化，也缺少逐包和跨轮依赖失效证据。若只按源码包摘要拼接成功，会掩盖未执行操作或把旧兄弟包结果当作本次验收。

下一步应先定义每个测试实际执行操作的映射、目录版本与传递依赖指纹，再把跨轮汇总的来源与失效理由写入检查记录。交付仍强制当前源码完整执行，不沿用旧结果。本次不扩大到业务缓存或正式运行逻辑。
