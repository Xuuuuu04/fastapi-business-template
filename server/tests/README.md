# tests：测试

| 目录 | 检查什么 | 何时运行 |
| --- | --- | --- |
| framework | 框架自身：执行器、声明检查、步骤约束、参数注入、任务、大模型入口、运行记录及其故障、命令行工具；含故意写错的反例 | 默认全量 |
| modules | 按模块测试业务规则，用和用户确认过的样例 | 默认全量 |
| integration | 从真实的应用工厂和 HTTP 入口测试完整流程 | 默认全量 |
| contracts | 可替换的实现遵守同一约定：运行记录的内存和数据库保存、进程内缓存和 Redis、本地目录和 S3 文件存储 | 默认全量；Redis、S3 需设置环境变量 |
| architecture | 依赖方向、模块登记、迁移与表定义一致、框架文件摘要、项目工具；在项目副本中走一遍“生成新模块、生成迁移、模块单独检查、全部测试” | 完整检查才跑完整副本路径；耗时以实际记录为准 |
| quality | 代码、命名、README、业务文档的质量规则，以及每条规则的反例 | 默认全量 |
| security | 身份与权限、生产配置、敏感字段、错误不外露、请求限制 | 默认全量 |
| recovery | 提交时断连、worker 停止、规则变化后重复请求 | 默认全量 |
| load | 压力测试，需要先启动服务 | 手动，发布前 |
| browser | 浏览器检查接口文档页面，需要 Playwright | 手动 |
| temp | 临时复现问题的脚本，不进入版本管理的正式测试 | 手动 |

- 包内调试：`uv run dev check --quick --module 包名`，只检查本包风格、格式和业务测试，不代表正式验收。
- 整层验收：`uv run dev check --module A --module B`，公共检查只跑一次，测试选择本层和受影响调用方，另做一次导入、登记与迁移一致性检查。无需每包重跑框架自身的全部测试。
- 自动选择：`uv run dev check --affected --base origin/main`，按修改前后依赖的并集选包；公共或未知变化完整检查。main 与手动 CI 完整，业务 PR 按影响范围，部署镜像仍检查。
- 完整检查：整批交付和发布前运行 `uv run dev check`，以上“默认全量”指这一级，不指每次包内修改。
- 默认新 SQLite 文件从空结构快照复制，结构或迁移版本变化时更新；自定义建表事件、已有文件、显式数据库和 PostgreSQL 仍完整重建。并行代理必须各用独立测试库，不能共享同一地址删表。
- 检查记录包含各项总耗时及测试 setup/call/teardown 耗时，方便区分准备与业务执行；旧记录缺失时不估算。快速结果不计为正式模块验收，也不覆盖完整检查状态。
- 新项目生成用例固定在自己的 SQLite 上检查（不验证 PostgreSQL）。默认测试成功后，追加 PostgreSQL 的第二轮不重复这条用例，并明确记录跳过原因；直接运行 PostgreSQL 测试或前轮失败时仍执行。其余真实数据库测试保持两库运行。

- 运行：`uv run python -m pytest -q`（在 server 目录）。设置 `APP_TEST_DATABASE_URL` 后，同一组测试在 PostgreSQL 上运行。
- 设置 `APP_TEST_REDIS_URL` 后测试 Redis 缓存；设置 `APP_TEST_S3_ENDPOINT`、`APP_TEST_S3_ACCESS_KEY`、`APP_TEST_S3_SECRET_KEY`（可选 `APP_TEST_S3_BUCKET`、`APP_TEST_S3_REGION`）后测试 S3 兼容存储。CI 使用固定版本的 SeaweedFS 提供 S3 服务。没有设置时这些测试跳过；生产使用 Redis 或 S3 时，发布前要设置后运行。
- 共用配置：[testing_app.py](testing_app.py)（测试密钥 `KEY`、只读密钥 `READER`）、[conftest.py](conftest.py)（`client`、`services`、`sample` 夹具）。
- 测试失败时，[failure_reports.py](failure_reports.py) 附中文运行报告，并把本测试全部运行及完整报告保存到 `var/development/failures/`；成员夹具销毁前补入阶段、成员、任务及租约状态，不保存身份或输入产出正文。先读报告再读代码。
- 成员链样例使用受控队列时钟，按下一任务的实际到期时间推进；机器停顿不消耗合成上游的20秒等待预算。超时前检查、提交时超时、租约重领和PostgreSQL并发提交另有明确样例，正式worker仍使用真实时间。
- 测试说明中写上规则编号（例如 `# R-03：……`），`doc/progress.md` 据此统计每条规则有没有测试。
- 业务测试的预期值来自已确认的业务样例，不要照着实现代码的公式反推预期。
