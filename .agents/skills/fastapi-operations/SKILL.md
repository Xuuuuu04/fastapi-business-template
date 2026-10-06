---
name: fastapi-operations
description: 查看运行报告、手动处理后台任务、生成服务密钥时使用。不负责业务迁移，也不代表有发布授权。
---

# 系统操作

在 `server/` 执行。这些命令读取当前 `APP_` 配置指向的数据库，运行前先确认连的是哪个环境。

```bash
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py diagnose --help
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py diagnose run 运行编号
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs list
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs show 任务编号
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py make_key --name 服务名 --org-id 组织 --permissions 权限
```

## 查运行情况

`diagnose` 有五个子命令：`runs`（运行列表）、`run`（单次运行）、`flow`（流程）、`field`（字段来源）、`stats`（统计）。也可以在浏览器打开 `/system/console`，或访问 `/api/system/runs/{run_id}/report`。

## 处理后台任务

`jobs list` 和 `jobs show` 只读。`jobs requeue`（重新排队）和 `jobs cancel`（取消）会修改任务，执行前先确认：

- 授权是否覆盖这个任务、这个环境。
- 重新排队前，先查任务里的外部动作是否已经执行。结果不明时不要直接重试，否则可能重复执行（比如重复扣款）。

后台任务使用用户权限的限制见 `server/shared/jobs/README.md`。

## 生成服务密钥

- 明文密钥只显示给请求的人。配置里保存摘要和明确的权限。
- 不要把明文密钥写进 Git、运行记录或文档。
- 生成密钥不等于部署配置已经完成。
- 打印环境信息、报告和示例时，不要带出连接密码或真实业务数据。
