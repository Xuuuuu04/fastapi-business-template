# 测试

测试在 `server/tests/`。`dev check --group` 按下表的分组只跑一部分；分组由文件位置决定，个别测试可以用 `@pytest.mark.test_group("组名")` 改组。

| 目录 | 分组 | 放什么 |
| --- | --- | --- |
| `modules/包名/test_calc*.py`、`unit/` | pure | 不碰数据库、网络、文件的纯计算和公开数据 |
| `modules/包名/` 其余文件 | module | 本包步骤和业务规则，用确认过的样例 |
| `integration/包名/`、`flows/` | flow | 从真实应用工厂和 HTTP 入口走完整流程，含权限和非法输入 |
| `framework/` | framework | 框架自身和各机制的独立样例，含故意写错的反例 |
| `architecture/`、`quality/`、`security/`、`recovery/`、`contracts/` | framework | 依赖方向与迁移一致性、代码和文档规则、身份与生产配置、断连与重启、可替换实现的同一组约定 |
| `load/`、`browser/`、`temp/` | 不在默认运行里 | 压力测试、浏览器检查、临时复现脚本 |

`dev check --module 包` 跑的是 `tests/modules/包/` 和 `tests/integration/包/`。生成器已经在这两处放好步骤测试和接口测试，新操作也会补上正常样例和规则异常样例。

## 写业务测试

- 夹具在 `tests/conftest.py`：`client`（真实应用的 TestClient）、`services`（组装好的服务，可直接 `await services.runtime.run(操作, 输入, caller=...)`）、`settings`。请求头用 `tests/testing_app.py` 的 `KEY`（全部权限）和 `READER`（只读）。
- 单个步骤用 `shared.flow.testing` 的 `try_step(步骤, Work类, 字段=值)`，返回的 `values` 是写出的字段；异步步骤用 `try_step_async(步骤, Work类, {字段: 值}, store=假存储)`。
- 接口测试除了正常结果，还要断言错误的 `code`；需要确认停在哪一步时，用响应里的 `run_id` 查 `/api/system/runs/{run_id}`。
- 只在 PostgreSQL 上有意义的测试（行锁、并发提交）加 `@pytest.mark.postgres_only`，没有配置 PostgreSQL 时会跳过。
- 临时复现脚本放 `tests/temp/`。问题查清后，能长期保护行为的改成正式测试放到对应目录，其余删除。

完整跑一遍测试（不指定文件、不过滤分组）时，app 里登记的每个操作至少要被执行一次，否则整轮失败并列出没执行到的操作名。按 `--module` 跑时只核对所选的包。

## 失败时看哪里

失败的测试会在输出里附上中文运行报告，并把这个测试里的全部运行和完整报告存成 `server/var/development/failures/随机名.json`。多阶段流程的测试还会补上阶段、成员、任务和租约状态。先读报告找到失败的步骤和源码行，再去读代码。

## 数据库

- 默认用 SQLite，每个测试拿到一个新文件。
- 用 PostgreSQL：`uv run dev check --postgres 地址`，或直接运行 pytest 时设置 `APP_TEST_DATABASE_URL`。每个 pytest 进程在这个地址上新建一个测试库，跑完删掉，所以账号需要建库权限。
- Redis 和 S3 的约定测试要设置 `APP_TEST_REDIS_URL`，以及 `APP_TEST_S3_ENDPOINT`、`APP_TEST_S3_ACCESS_KEY`、`APP_TEST_S3_SECRET_KEY`（可选 `APP_TEST_S3_BUCKET`、`APP_TEST_S3_REGION`），没设置时这些测试跳过。

## 手动测试

```bash
uv run python -m tests.load.run --port 8000 --key 服务密钥 --count 500 --workers 20
uv run --with playwright python -m playwright install chromium
uv run --with playwright python -m tests.browser.run --port 8000 --output out/browser
```

- 压力测试要先启动服务，结果用来比较改动前后。
- 浏览器检查要求服务开着 `APP_DOCS=true`；设置 `APP_TEST_SERVICE_KEY` 并开 `APP_CONSOLE=true` 时还会检查运行页面。
