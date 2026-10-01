# tests：测试

| 目录 | 检查什么 | 何时运行 |
| --- | --- | --- |
| framework | 框架自身：执行器、声明检查、步骤约束、参数注入、任务、大模型入口、运行记录及其故障、命令行工具；含故意写错的反例 | 默认全量 |
| modules | 按模块测试业务规则，用 doc/模块名/rules.md 中确认过的样例 | 默认全量 |
| integration | 从真实的应用工厂和 HTTP 入口测试完整流程 | 默认全量 |
| contracts | 可替换的实现遵守同一约定：运行记录的内存和数据库保存、进程内缓存和 Redis、本地目录和 S3 文件存储 | 默认全量；Redis、S3 需设置环境变量 |
| architecture | 依赖方向、模块登记、迁移与表定义一致、框架文件摘要、项目工具；在项目副本中走一遍“生成新模块、生成迁移、模块单独检查、全部测试” | 默认全量（副本路径约 9 秒） |
| quality | 代码、命名、README、业务文档的质量规则，以及每条规则的反例 | 默认全量 |
| security | 身份与权限、生产配置、敏感字段、错误不外露、请求限制 | 默认全量 |
| recovery | 提交时断连、worker 停止、规则变化后重复请求 | 默认全量 |
| load | 压力测试，需要先启动服务 | 手动，发布前 |
| browser | 浏览器检查接口文档页面，需要 Playwright | 手动 |
| temp | 临时复现问题的脚本，不进入版本管理的正式测试 | 手动 |

- 运行：`uv run python -m pytest -q`（在 server 目录）。设置 `APP_TEST_DATABASE_URL` 后，同一组测试在 PostgreSQL 上运行。
- 设置 `APP_TEST_REDIS_URL` 后测试 Redis 缓存；设置 `APP_TEST_S3_ENDPOINT`、`APP_TEST_S3_ACCESS_KEY`、`APP_TEST_S3_SECRET_KEY`（可选 `APP_TEST_S3_BUCKET`、`APP_TEST_S3_REGION`）后测试 S3 兼容存储。CI 使用固定版本的 SeaweedFS 提供 S3 服务。没有设置时这些测试跳过；生产使用 Redis 或 S3 时，发布前要设置后运行。
- 共用配置：[testing_app.py](testing_app.py)（测试密钥 `KEY`、只读密钥 `READER`）、[conftest.py](conftest.py)（`client`、`services`、`sample` 夹具）。
- 测试失败时，[failure_reports.py](failure_reports.py) 把本测试中失败运行的中文报告附在失败输出里，先读报告再读代码。
- 测试说明中写上规则编号（例如 `# R-03：……`），`doc/progress.md` 据此统计每条规则有没有测试。
- 业务测试的预期值来自已确认的业务样例，不要照着实现代码的公式反推预期。
