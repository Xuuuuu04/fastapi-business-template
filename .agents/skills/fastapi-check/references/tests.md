# 测试

测试放在 `server/tests/`。`dev check --group` 按下表目录只跑指定分组，个别测试可通过 `@pytest.mark.test_group("组名")` 改组。

| 目录 | 分组 | 放什么 |
| --- | --- | --- |
| `modules/包名/test_calc*.py`、`unit/` | `pure` | 不依赖数据库、网络和文件的纯计算与公开数据 |
| `modules/包名/` 其余文件 | `module` | 本包步骤和业务规则，使用确认过的样例 |
| `integration/包名/` | `flow` | 从真实应用工厂和 HTTP 入口走通完整流程，含权限与校验错误 |
| `framework/` | `framework` | 框架自身和各项功能的独立样例，含故意写错的反例 |
| `architecture/`、`quality/`、`security/`、`recovery/`、`contracts/` | `framework` | 依赖方向与迁移检查、代码和文档规则、身份与生产配置、断连恢复、多实现通用契约 |
| `load/`、`browser/`、`temp/` | 不在默认运行里 | 压测与浏览器检查；临时试验脚本放系统临时目录 |

`dev check --module 包` 只运行 `tests/modules/包/` 与 `tests/integration/包/`。跑完整全仓测试时，app 里登记的每个操作至少要执行一次，否则整轮测试会列出漏测操作名并报错。

## 写业务测试

- 测试准备函数在 `tests/conftest.py`：`client`（应用 `TestClient`）、`services`（可直接 `await services.runtime.run(...)`）、`settings`；请求头使用 `tests/testing_app.py` 的 `KEY`（全部权限）和 `READER`（只读）。
- 测单个步骤使用 `shared.flow.testing` 的 `try_step(步骤, Work类, 字段=值)` 或异步版 `try_step_async`。
- 接口测试除正常路径外，还要断言错误 `code`；想追查停在哪一步，按响应里的 `run_id` 查询 `/api/system/runs/{run_id}`。
- 依赖 PostgreSQL 锁行为的测试标上 `@pytest.mark.postgres_only`，未配 PostgreSQL 时跳过。
- 失败测试会打印中文运行报告，并把完整记录保存为 `server/var/development/failures/随机名.json`。

## 数据库与外部依赖

- 默认使用 SQLite，每个测试独立建库文件。
- 跑 PostgreSQL 测试：执行 `uv run dev check --postgres 测试库地址`，或在直接运行 pytest 时设置 `APP_TEST_CONTROL_URL`。每个 pytest 进程会在该地址下新建并清理独立测试库，账号需要建库权限。
- 跑 Redis 和 S3 适配器契约测试时设置 `APP_TEST_REDIS_URL`、`APP_TEST_S3_ENDPOINT`、`APP_TEST_S3_ACCESS_KEY`、`APP_TEST_S3_SECRET_KEY`（可选 `APP_TEST_S3_BUCKET`、`APP_TEST_S3_REGION`）。

## 手动压测、浏览器检查与性质测试

```bash
uv run python -m tests.load.run --port 8000 --key 服务密钥 --path /api/v1/待测接口 --count 500 --workers 20
uv run --with playwright python -m playwright install chromium
uv run --with playwright python -m tests.browser.run --port 8000 --output out/browser
```

- 浏览器检查需要开启 `APP_DOCS=true`；设置 `APP_TEST_SERVICE_KEY` 且开启 `APP_CONSOLE=true` 时会一并检查运行排查台。
- 性质测试示例见 `tests/framework/test_properties.py`（纯计算最多 40 个样例，数据库测试最多 8 个）。金额比较、排序与聚合以及并发锁业务，需要跑 `dev check --postgres 地址` 验证，因为 SQLite 的 `ExactNumber` 以文本存储。
- CI 的快速作业只跑静态检查和 SQLite 测试；PostgreSQL 17 作业独立运行全量测试，Redis/S3 适配器检查需手动触发。
