# deploy：部署

| 文件 | 用途 |
| --- | --- |
| [Dockerfile](Dockerfile) | 接口和 worker 共用的镜像，非 root 用户运行 |
| [compose.yaml](compose.yaml) | 单机部署：PostgreSQL、迁移、接口、worker |
| [check_env.py](check_env.py) | 部署前的环境检查：`uv run python -m deploy.check_env` |
| [backup.md](backup.md) | 备份、恢复演练和代码回退 |

## 单机部署步骤

```bash
cp .env.example .env              # 按注释填写生产配置，设置 DATABASE_PASSWORD
uv run python -m tools.make_key --name admin --permissions "*"   # 生成服务密钥，写入 APP_API_KEYS
docker compose -f deploy/compose.yaml --env-file .env up -d --build
curl http://127.0.0.1:8000/health/ready
```

迁移由 `migrate` 服务在接口和 worker 启动前执行一次；接口和 worker 不会自己改表结构。

## 运行方式与不能承诺的事

| 方式 | 适合 | 不能承诺 |
| --- | --- | --- |
| 本地开发（SQLite，单进程） | 开发和体验 | 与生产行为完全相同 |
| 单机部署（本 compose） | 小规模生产 | 机器故障时不中断 |
| 多实例 | 接口按负载加实例；worker 可以多个（需要 PostgreSQL） | 只加容器就能扩容；数据库本身的高可用需要另外配置 |

- 同一台机器的连接总数 = 每个进程的 `APP_DATABASE_POOL_SIZE` × 进程数，要小于 PostgreSQL 的 `max_connections`，并留出迁移和运维的余量。
- `mem_limit` 等资源限制是示例值，按实测调整。
- 生产环境要求：PostgreSQL、运行记录保存到数据库、至少一把服务密钥、写入代码版本；不满足时服务拒绝启动。
- 前端还没有开发，所以这里没有前端部署脚本；有前端时在这里增加。
