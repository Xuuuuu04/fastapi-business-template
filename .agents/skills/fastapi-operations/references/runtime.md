# 运行参考

命令都在 `server/` 执行。

## 进程

- 接口进程：`uv run uvicorn app.setup.web:create_app --factory`。worker：`uv run python -m app.setup.worker`。两者用同一个 `build()` 组装。`uv run dev inspect` 显示产品实际组装了哪些模块、路由、worker 和供应商。
- 启动时检查全部登记包的结构和生产配置，不合格就拒绝启动。创建服务时不连数据库，也不自动迁移。
- 任务表就是队列。没有 worker 运行时，后台任务、定时计划和多阶段流程都不会推进。

## 生产配置

`APP_ENV=production` 时，下面任何一项不满足，服务拒绝启动：

| 配置 | 要求 |
| --- | --- |
| `APP_DATABASE_URL` | PostgreSQL |
| `APP_DEV_CALLER` | 关闭 |
| `APP_RUN_RECORDS` | `database` |
| `APP_API_KEYS` | 至少一把，用 `dev make-key` 生成，只存摘要 |
| `APP_CODE_VERSION` | 部署的提交号，`dev deploy` 自动传入 |
| `APP_JWT_SECRET` | 独立随机，至少 32 个字符；换密钥时旧的放进 `APP_JWT_PREVIOUS_SECRETS` |
| `APP_DATA_KEYS` | 有存储用 `vault` 时必须独立设置，至少 32 个字符；新密钥放第一位 |
| 模型配置、`APP_REMOTES` | 声明了提示词或外部系统就必须配置 |

其他要按目标环境确认的配置：

- 公开访问：`FORWARDED_ALLOW_IPS` 只写实际代理地址；HTTPS 确认后再设 `APP_HSTS_SECONDS`；明确设置 `APP_CORS`、`APP_DOCS`。`APP_CONSOLE` 在生产默认关闭，其他环境默认打开。
- 容量：各进程 `APP_DATABASE_POOL_SIZE` 之和要低于 PostgreSQL 的 `max_connections` 并留余量。`APP_MAX_INFLIGHT`、`APP_JOB_CONCURRENCY`、`APP_HEAVY_CONCURRENCY`（默认每进程 4）、模型和外部并发按实测设置。
- 多实例：要用 PostgreSQL；共用 Redis（`APP_CACHE_URL`）才能共享限流计数；本地文件要共用卷，或改用 S3。SQLite 只能跑一个 worker。
- 多组织定时用 `APP_SCHEDULE_ORG_IDS=["alpha","beta"]`。产品自己的 PostgreSQL 行级策略用 `APP_DATABASE_ORG_SETTING`，策略和角色由产品迁移创建并另行验证。
- `APP_DISABLED_MODULES` 关闭模块入口，不撤销表归属，也不跳过结构检查。

## 单机部署

日常用 `uv run dev deploy`（见 [SKILL](../SKILL.md)“发布上线”）。它在服务器上执行的就是 `docker compose -f deploy/compose.yaml --env-file .env up -d --build`，再等 `/health/ready`。

- `migrate` 服务先执行迁移，接口和 worker 不自己改表。接口端口只绑定宿主机 `127.0.0.1:8000`，对外要配 HTTPS 反向代理，前端和 `/api` 放同一域名。
- worker 健康：设置 `APP_JOB_HEALTH_FILE`（放 worker 自己的临时目录），用 `python -m app.setup.worker_health` 检查，默认 60 秒内有更新才算健康。显示 unhealthy 时 Docker 不会自动重启。
- 停止：worker 先等在途任务 `APP_JOB_SHUTDOWN_SECONDS`（默认 20 秒），超时再取消并清理。容器的 `stop_grace_period`（模板 30 秒）要比它长，否则清理会被强杀打断。

## 迁移

- compose 的 `migrate` 服务执行 `alembic upgrade head`。`/health/ready` 会核对数据库版本和代码是否一致。
- 模板初始迁移 `7e03c1a0b624` 只用于全新数据库。已有产品保留自己的迁移链。
- 迁移里的删除、改名、改类型默认只警告。逐条整理好历史表归属（`APP_OWNED_TABLES`、`APP_EXTERNAL_TABLES` 或模块的同名登记）后，设 `APP_MIGRATION_STRICT=true` 把警告变成错误。

## 运行记录和日志

- 运行记录要跨进程查看（接口进程看 worker 的进度），必须 `APP_RUN_RECORDS=database`；用内存时重启就丢。保留天数是 `APP_RUN_RECORD_DAYS`。
- 记录可能丢失或过期清理，业务结果以业务表和任务表为准。超过五分钟没有上报的运行显示"失去联系"，这不能证明失败，要再查任务和业务数据。
- 日志在生产是一行一条 JSON，带请求编号，不含请求正文、密钥和业务原文；意外异常只有类型和文件行号。`APP_OTEL_ENDPOINT` 配置后导出跨度。

## 用系统接口逐层查一次运行

起点是错误响应里的 `run_id`，或响应头的 `X-Request-ID`、`X-Run-ID`。没有 `X-Run-ID` 说明请求没进入登记的操作（认证失败、路由不存在），按请求编号查日志。`/system/console` 页面展示同样的数据。

| 顺序 | 接口 | 看什么 | 权限 |
| --- | --- | --- | --- |
| 1 | `GET /health/live`、`GET /health/ready` | 进程是否活着，数据库能否连通、迁移是否到位 | 公开 |
| 2 | `GET /api/system/runtime` | 内存、在途请求、连接池、记录缓冲、任务数量、熔断状态 | `system.diagnostics` |
| 3 | `GET /api/system/runs?request_id=&job_id=&module=&contract=&status=` | 按条件找到运行编号和中文摘要 | `system.diagnostics` |
| 4 | `GET /api/system/runs/{run_id}`、`.../report` | 完整调用树和运行图；Markdown 报告写明停在哪一步、为什么 | `system.diagnostics` |
| 5 | `GET /api/system/flows/{操作名}`、`/api/system/fields/{操作名}/{字段}`、`/api/system/modules` | 声明上的步骤、字段来源、模块关系，和第 4 步对照 | `system.diagnostics` |
| 6 | `GET /api/system/stats` | 按操作和状态汇总已结束的运行 | `system.diagnostics` |
| 7 | `GET /api/jobs/{id}`、`/api/jobs/{id}/segments`、`/api/system/jobs?state=&contract=` | 任务状态、已提交的批次 | 登记者本人或 `system.jobs` |
| 8 | `GET /api/system/pipelines`、`/{id}`、`/{id}/members?stage=` | 流程阶段、扇出成员、每段运行编号 | `system.diagnostics` |
| 9 | `GET /api/system/audit`、`/api/system/changes?table=&key=` | 操作记录和数据变更历史 | `system.audit` |

查询接口都是只读的。恢复流程用 `POST /api/system/pipelines/{id}/resume`（另需 `system.pipelines`）或 `dev pipelines resume`；重新排队、取消任务只能用命令行。

## 补充命令

```bash
uv run dev jobs segments 任务编号
uv run dev jobs resource model --capacity 4 --yes
uv run dev pipelines members 流程编号 阶段名
uv run dev diagnose budgets --runtime-config
```

- `jobs resource` 改跨 worker 的资源额度，先停旧 worker、等在途位置结束再执行。`jobs cancel` 只能取消还没开始的任务。
- `diagnose budgets` 离线列出排队、执行、外部调用、有效期等各类预算和声明位置；加 `--runtime-config` 才读取运行配置，不连数据库。
