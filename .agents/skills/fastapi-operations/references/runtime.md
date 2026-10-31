# 运行参考

命令都在 `server/` 执行。

## 进程

- 接口进程：`uv run uvicorn app.setup.web:create_app --factory`。worker：`uv run python -m app.setup.worker`。两者通过同一个 `build()` 创建服务。`uv run dev inspect` 显示产品启用了哪些模块、路由、后台执行进程和外部服务。
- 启动时检查全部登记包的结构和生产配置，不合格就拒绝启动。创建服务对象时不连接数据库，也不自动迁移。
- 任务表就是队列。没有 worker 运行时，后台任务、定时计划和多阶段流程都不会推进。

## 生产配置

`APP_ENV=production` 时配置不合格，服务拒绝启动。服务器的 `server/.env` 要写：

| 配置 | 要求 |
| --- | --- |
| `DATABASE_PASSWORD` | 数据库密码，compose 用它创建数据库并生成连接地址 |
| `APP_API_KEYS` | 至少一把，用 `dev make-key` 生成，只存摘要 |
| `APP_JWT_SECRET` | 独立随机，至少 32 个字符；换密钥时旧的放进 `APP_JWT_PREVIOUS_SECRETS` |
| `APP_DATA_KEYS` | 存储用了 `vault` 或产品登记了 `providers` 时必须写，每把至少 32 个字符，新密钥放第一位 |
| 模型配置、`APP_REMOTES` | 声明了提示词或外部系统就必须写 |

`APP_ENV`、`APP_DATABASE_URL`、`APP_RUN_RECORDS`、`APP_CODE_VERSION` 和文件目录由 `deploy/compose.yaml` 设好，不用写。

按实际环境再确认：

- 公开访问：`FORWARDED_ALLOW_IPS` 只写实际代理地址；HTTPS 确认后再设 `APP_HSTS_SECONDS`；明确设置 `APP_CORS`、`APP_DOCS`。`APP_CONSOLE` 在生产默认关闭。
- 连接数和并发数：各进程 `APP_DATABASE_POOL_SIZE` 之和要低于 PostgreSQL 的 `max_connections`。`APP_MAX_INFLIGHT`、`APP_JOB_CONCURRENCY`、`APP_HEAVY_CONCURRENCY`（默认每进程 4）、模型和外部并发按实测设置。
- 多实例：共用 Redis（`APP_CACHE_URL`）才能共享限流计数；本地文件要共享存储目录，或改用 S3。SQLite 只支持运行一个 worker。
- 多组织定时用 `APP_SCHEDULE_ORG_IDS=["alpha","beta"]`。PostgreSQL 按行限制数据访问的策略用 `APP_DATABASE_ORG_SETTING`，策略和角色由产品迁移创建。
- `APP_DISABLED_MODULES` 关闭模块入口，不改变表的所属模块，也不跳过结构检查。

## compose 部署

`deploy/compose.yaml` 有数据库、迁移、接口、worker 四个服务，用同一个镜像和同一份配置。

- `migrate` 服务执行 `alembic upgrade head`，接口和 worker 等它成功后才启动。`/health/ready` 会核对数据库版本和代码是否一致。
- 接口端口只绑定宿主机 `127.0.0.1:8000`，数据库只绑定 `127.0.0.1:5432`。对外要配 HTTPS 反向代理，前端和 `/api` 放同一域名。
- worker 健康：compose 设了 `APP_JOB_HEALTH_FILE`，用 `python -m app.setup.worker_health` 检查，默认 60 秒内有更新才算健康。显示 unhealthy 时 Docker 不会自动重启。
- 停止：worker 先等待正在执行的任务，最多等待 `APP_JOB_SHUTDOWN_SECONDS`（默认 20 秒），超时再取消并清理。compose 的 `stop_grace_period` 设为 30 秒，要比它长。分段任务每批的耗时要小于这两个值中较小的那个。

## 迁移

- 迁移只能改本产品登记的表：模块的 `tables` 和 `owned_tables`；模块 `external_tables` 里的表只读。迁移删除、改名、改类型没有登记的表时，启动和检查都会报错。

## 运行记录和日志

- 运行记录要跨进程查看（接口进程看 worker 的进度），必须 `APP_RUN_RECORDS=database`；只存在内存时，重启后记录会丢失。保留天数是 `APP_RUN_RECORD_DAYS`。
- 记录可能丢失或过期清理，业务结果以业务表和任务表为准。超过五分钟没有更新的运行显示"失去联系"，此时应继续查询任务和业务数据，确认实际结果。
- 日志在生产是一行一条 JSON，带请求编号，不含请求正文、密钥和业务原文；意外异常只有类型和文件行号。设置 `APP_OTEL_ENDPOINT` 后，会向该地址发送调用耗时与关联信息（OpenTelemetry span）。

## 用系统接口查一次运行

起点是错误响应里的 `run_id`，或响应头的 `X-Request-ID`、`X-Run-ID`。没有 `X-Run-ID` 说明请求没进入登记的操作（认证失败、路由不存在），按请求编号查日志。`/system/console` 页面展示同样的数据。

| 顺序 | 接口 | 看什么 | 权限 |
| --- | --- | --- | --- |
| 1 | `GET /health/live`、`GET /health/ready` | 进程是否运行，数据库能否连通、迁移是否到位 | 公开 |
| 2 | `GET /api/system/runtime` | 内存、执行中的请求、连接池、待保存的运行记录、任务数量、故障暂停状态 | `system.diagnostics` |
| 3 | `GET /api/system/runs?request_id=&job_id=&module=&contract=&status=` | 按条件找到运行编号和中文摘要 | `system.diagnostics` |
| 4 | `GET /api/system/runs/{run_id}`、`.../report` | 完整的操作调用关系和执行图；Markdown 报告写明停在哪一步、为什么 | `system.diagnostics` |
| 5 | `GET /api/system/flows/{操作名}`、`/api/system/fields/{操作名}/{字段}`、`/api/system/modules` | 代码声明的步骤、字段来源、模块关系，和第 4 步对照 | `system.diagnostics` |
| 6 | `GET /api/system/stats` | 按操作和状态汇总已结束的运行 | `system.diagnostics` |
| 7 | `GET /api/jobs/{id}`、`/api/jobs/{id}/segments`、`/api/system/jobs?state=&contract=` | 任务状态、已提交的批次 | 登记者本人或 `system.jobs` |
| 8 | `GET /api/system/pipelines`、`/{id}`、`/{id}/members?stage=` | 流程阶段、并行子任务、各阶段的运行编号 | `system.diagnostics` |
| 9 | `GET /api/system/audit`、`/api/system/changes?table=&key=` | 操作记录和数据变更历史 | `system.audit` |

查询接口都是只读的。恢复流程用 `POST /api/system/pipelines/{id}/resume`（另需 `system.pipelines`）或 `dev pipelines resume`；重新排队、取消任务只能用命令行。

## 补充命令

```bash
uv run dev jobs segments 任务编号
uv run dev jobs resource model --capacity 4 --yes
uv run dev pipelines members 流程编号 阶段名
uv run dev diagnose budgets --runtime-config
```

- `jobs resource` 改所有 worker 共用的资源并发上限，先停旧 worker、等待正在占用资源的任务结束再执行。
- `diagnose budgets` 离线列出排队、执行、外部调用、有效期等各类时间或次数限制，以及声明位置；加 `--runtime-config` 才读取运行配置，不连数据库。
