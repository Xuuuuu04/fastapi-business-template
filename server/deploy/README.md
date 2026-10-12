# deploy：部署

普通正文和上传正文的累计读取期限分别由 `APP_BODY_TIMEOUT_SECONDS`、`APP_UPLOAD_TIMEOUT_SECONDS` 控制（默认 30/120 秒）；涓滴输入不能不断延长额度，完成输入后的长响应不受这个期限限制。Redis 操作总期限与连接预算按实例配置，缓存不可用时认证返回 503。

本后端是空业务模板，提供 HTTP、事务、后台任务、令牌校验和文件存储等公共能力。当前没有预置账号登录、用户管理或文件业务接口。

配套 Vue3 前端模板已有界面和独立演示服务。产品集成前，需要增加自己的登录、权限及文件业务，确认接口路径、字段、上传格式和错误响应，再按生成的 OpenAPI 同步前端。前端生产构建使用 `VITE_API_MODE=real`；演示页面可用不代表真实业务已接通。具体约定见 [前后端对接 Skill](../../.agents/skills/fastapi-module/references/frontend-interface.md)。

| 文件 | 用途 |
| --- | --- |
| [Dockerfile](Dockerfile) | 接口和 worker 共用的镜像，非 root 用户运行 |
| [compose.yaml](compose.yaml) | 单机部署：PostgreSQL、迁移、接口、worker |
| [check_env.py](check_env.py) | 配置、数据库、迁移版本与磁盘检查 |
| [backup.md](backup.md) | 数据库与文件备份、恢复演练和代码回退 |

## 准备生产配置

以下命令在 `server/` 执行。首次准备配置时复制 [环境样例](../.env.example)，已有 `.env` 按需更新，不覆盖：

```bash
cp .env.example .env
```

填写目标环境的配置后再启动：

- 设置独立的 `DATABASE_PASSWORD`、`APP_JWT_SECRET` 和实际部署的 `APP_CODE_VERSION`，关闭 `APP_DEV_CALLER`。本 Compose 为容器设置生产环境、PostgreSQL 和数据库运行记录；单独运行服务时也需明确配置这些项。
- 当前和轮换旧 JWT 密钥都应独立随机生成、至少 32 个字符。生产启动检查会拒绝模板公开的本机开发密钥、过短的当前或旧密钥。`APP_JWT_PREVIOUS_SECRETS` 只保留仍处于轮换过渡期的真实生产密钥，过渡结束后移除。
- 生产环境至少配置一把服务密钥。通过 [系统操作 Skill](../../.agents/skills/fastapi-operations/SKILL.md) 生成，按实际用途指定权限和组织；配置中只保存摘要。生成密钥本身不能证明部署安全，不把全权限、全组织管理员密钥作为默认配置。
- 浏览器通过产品登录取得短期令牌。服务密钥用于服务器调用，不写入前端源码或构建变量。
- 业务使用字段加密时配置独立的 `APP_DATA_KEYS`；使用文件、缓存、大模型或外部接口时填写对应真实服务配置。模板样例中的地址、密钥和本机文件目录不能代替目标环境配置。

## 单机部署步骤

```bash
docker compose -f deploy/compose.yaml --env-file .env up -d --build
docker compose -f deploy/compose.yaml --env-file .env exec -T api python -m deploy.check_env
curl --fail http://127.0.0.1:8000/health/ready
```

`migrate` 服务在接口和 worker 启动前执行迁移；接口和 worker 不会自己改表。模板的初始迁移用于全新数据库，已有产品保留自己的迁移历史，发布前先在隔离数据库验证迁移和恢复。

本地文件和上传临时区使用共用的 `files` 卷，重建容器后仍可读取；选用 S3 时正式文件保存在对象存储。数据库和文件要一起备份并演练恢复，见 [备份与恢复](backup.md)。

Compose 只把接口端口绑定到宿主机 `127.0.0.1:8000`。对外访问需要配置 HTTPS 反向代理；前端静态文件和 `/api` 可由同一域名提供。上述环境检查和就绪响应只说明配置、数据库及迁移状态，不代表产品业务、外部服务或公开访问已验收。

## 内置定时运维

按[备份与恢复](backup.md)设置APP_OPERATIONS：备份与隔离恢复验证、分段数据保留、容量提醒/非关键任务暂停、Webhook投递均可独立关闭，默认关闭保证旧产品行为。开启后必须运行worker；接口只负责查看，所有计划在框架module.py声明并进入运行图。执行迁移授权新system_ops_state表，所有worker使用相同配置与代码；JobPlan(critical=False)才允许容量暂停。

备份目录放在持久化卷，不得嵌入正式文件/上传目录；PG客户端及随机恢复库权限在隔离环境先验证。S3和真实提醒目标、生产账号、异地恢复/机器故障还需真实环境验证，pending通知不代表已经送达，归档存在不代表恢复成功。不要把运维任务已完成误称产品已部署或已验收。

## 资源、连接与多实例

| 方式 | 适合 | 需要另外确认 |
| --- | --- | --- |
| 本地开发，SQLite | 开发和体验，最多一个 worker 进程 | PostgreSQL 的并发与事务行为 |
| 单机 Compose | 单机产品部署 | 目标机器容量、备份和机器故障恢复 |
| 多实例 | 按实测增加接口或 worker 进程，使用 PostgreSQL | 共享限流、文件存储及数据库可用性 |

- 同一数据库的应用连接预算是各进程 `APP_DATABASE_POOL_SIZE` 的总和；接口和 worker 都占预算。保持低于 PostgreSQL 的 `max_connections`，为迁移、运维及其他使用者留余量。
- Compose 的内存限制是示例值。按实际业务测量请求、任务、文件和模型调用的资源消耗，再设置 `APP_MAX_INFLIGHT`、`APP_JOB_CONCURRENCY`、模型与外部服务并发。
- `APP_JOB_SHUTDOWN_SECONDS` 控制停止时等待任务正常完成的时间；超时后还要等待取消清理。容器或进程管理器的退出宽限时间应容纳回滚和连接释放，避免强制退出打断清理。
- 多个接口进程共用 Redis 缓存才能共享限流计数；不配置 `APP_CACHE_URL` 时，计数只在本进程内有效。本地文件存储需要共用文件卷，或改用 S3 兼容存储。
- 无效密钥和令牌按来源限流，正常账号使用独立额度。Redis 递增和有效期原子完成，不延长已有窗口，并修复旧的无有效期计数键。公开入口仍需按实际流量设置代理连接与请求限制，应用计数不能代替网络防护。
- 外部接口与模型响应按解压后实际字节设置上限，结合各自并发与期限控制内存。按每进程并发和响应上限估算资源预算，再在目标机器实测；这里的配置不能证明实际容量。
- Compose 为 worker 单独检查 `/tmp` 健康信号，接口健康不会掩盖 worker 停止工作。健康失败会显示 `unhealthy`；Docker 的 `restart: unless-stopped` 不会仅因这个状态自动重启，告警和恢复由实际部署安排。

## 公开访问与发布检查

- 只把实际受信任的代理地址写入 `FORWARDED_ALLOW_IPS`。代理地址未配置时，按地址的限流可能被所有用户共用；信任任意来源则可能接受伪造来源地址。
- 在实际代理路径检查 `APP_REQUEST_RATE_PER_MINUTE`、`APP_LOGIN_FAILURE_LIMIT`、`APP_LOGIN_ACCOUNT_FAILURE_LIMIT`、请求大小和并发限制。HTTPS 已确认后再设置 `APP_HSTS_SECONDS`。
- 明确设置 `APP_CORS` 和 `APP_DOCS`；生产排查页默认关闭，需要开放时配置 `APP_CONSOLE` 并限制入口访问。
- 按启用业务填写 `APP_REMOTES`、模型服务、Redis 与 S3 配置，在获准的隔离环境实际验证权限、超时和失败处理。环境检查不能代替这些服务的真实请求验证。
- 发布前运行 [完整检查](../../.agents/skills/fastapi-check/SKILL.md)，使用已授权的隔离 PostgreSQL 验证；按 [浏览器检查](../tests/browser/README.md) 验证接口与运行页面。产品还需验证真实登录、权限、文件操作、任务重启和备份恢复。

本地测试、隔离环境集成、远端检查、部署和产品验收分别记录。发布依据应对应当前代码、配置、目标环境和实际业务。
