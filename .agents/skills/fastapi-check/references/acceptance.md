# 前后端隔离验收

在 `server/` 执行以下命令启动本轮隔离后端服务：

```bash
uv run dev acceptance-server --port 0 --run-id 本轮编号
uv run dev acceptance-server --port 0 --run-id 本轮编号 --seed
uv run dev acceptance-server --port 0 --run-id 本轮编号 --lifecycle-file /本轮报告目录/backend.json
```

本轮编号只使用英文字母、数字、下划线和连字符，最多 80 个字符。端口传 0 时由系统分配；服务只监听 `127.0.0.1`，指定端口被占用时直接报错退出，不复用已有服务。启动日志出现 `acceptance_starting` 后，调用方要请求 `/health/ready` 并核对状态码和 `X-Acceptance-Run` 响应头。

传 `--lifecycle-file` 时指向报告目录中尚未创建的新文件。服务建好临时目录后原子写入 `run_id`、`folder` 和 `phase: "created"`；退出并删净目录后再原子更新为 `phase: "cleanup_complete"`。进程退出后你要再核对状态文件和目录是否已清理。

## 数据与身份

服务固定使用产品的 `ApplicationSpec.settings("test")`，不读取外部 `.env` 或环境变量，也不允许注入自定义外部适配器或模型工厂。

命令每轮会用已登记表结构创建全新的临时 SQLite 并写入结构版本，只启动单进程 HTTP 接口，不执行 Alembic 迁移，也不启动后台 worker；迁移、PostgreSQL 并发和后台任务需另跑对应测试。

传 `--seed` 时加载产品 `server/tests/acceptance/seed.py` 里的 `async prepare(services, folder)` 生成本轮账号与数据。需要让浏览器读取测试凭据时，把凭据文件放在传入的临时目录里（仅当前用户可读），不将密码和令牌写入日志或截图。

## 执行与完成

1. **核对就绪与实例头**。记录启动进程号和本轮编号，确认 `/health/ready` 和 `X-Acceptance-Run` 一致后再跑浏览器步骤。
2. **通过真实界面操作并查询核对**。用浏览器登录页面并完成完整业务动作，再通过正式查询接口核对数据库写入结果。
3. **停止进程并核对清理完成**。测试结束或中断时向服务进程发送 `SIGTERM` 或 `SIGINT`，等待退出并核对临时目录已删除；如果进程被强杀或断电中断，由调用方按记录下的临时目录手工清理。
