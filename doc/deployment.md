# 部署与线上运行排查

这份说明概括如何使用内置 Docker Compose 部署生产环境，以及如何通过命令行和系统接口定位运行问题。完整的环境变量要求、进程启停参数与诊断接口列表见 [运行参考](../.agents/skills/fastapi-operations/references/runtime.md)。

## 容器化部署结构

`server/deploy/compose.yaml` 使用同一份构建镜像编排四个服务：

1. `postgres`：PostgreSQL 17 数据库，仅绑定宿主机 `127.0.0.1:5432`。
2. `migrate`：启动时执行 `alembic upgrade head`，迁移成功后自动退出。
3. `api`：等 `migrate` 成功后启动 FastAPI 接口服务，仅绑定宿主机 `127.0.0.1:8000`，对外由宿主机 HTTPS 反向代理转发。
4. `worker`：等 `migrate` 成功后启动后台执行进程，负责推进异步任务、定时计划（`Schedule`）与多阶段流程（`Pipeline`），并通过健康文件持续上报心跳。

## 上线前必填配置

`APP_ENV=production` 启动时会自动校验生产配置，缺失任一项都会拒绝启动：

- `DATABASE_PASSWORD`：数据库密码。
- `APP_API_KEYS`：至少配置一把由 `uv run dev make-key` 生成的服务密钥摘要。
- `APP_JWT_SECRET`：长度不少于 32 个字符的独立随机签名密钥。
- `APP_DATA_KEYS`：使用 `Vault` 加密字段或外部 `ProviderSpec` 时必填，每把不少于 32 个字符。
- `APP_REMOTES` 与模型配置：业务模块声明了外部接口或提示词时必须提供对应地址与凭据。

多实例水平扩展时，需配置共用 Redis（`APP_CACHE_URL`）共享限流计数，并将文件存储切为共享目录或 S3 兼容对象存储（`APP_FILE_STORAGE=s3`）。

## 线上诊断与排查顺序

本地开发默认开启 `/system/console` 排查网页；生产环境默认关闭该网页，改用只读诊断接口或 `server/` 下的 `uv run dev` 命令排查：

1. 从客户端报错正文或响应头拿到 `X-Run-ID`（未进入业务操作时拿 `X-Request-ID` 查 JSON 日志）。
2. 请求 `GET /health/live` 与 `GET /health/ready` 确认进程存活、数据库连接及迁移版本一致。
3. 使用具有 `system.diagnostics` 权限的凭据访问 `GET /api/system/runs/{run_id}/report`（或在服务器执行 `uv run dev diagnose`），直接读取停在哪一步、执行了哪些 SQL、耗时多少毫秒。
4. 后台任务与多阶段流程分别通过 `uv run dev jobs` 和 `uv run dev pipelines` 查看批次进度、卡住原因或从失败阶段恢复执行。
