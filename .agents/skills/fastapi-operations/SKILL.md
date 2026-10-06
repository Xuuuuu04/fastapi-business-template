---
name: fastapi-operations
description: 查询本项目运行报告、人工处理后台任务或生成组织范围服务密钥时使用；不提供业务迁移或发布授权。
---

# 系统操作

在 `server/` 执行，下列查询使用当前 APP_ 配置，先确认数据库环境：

```bash
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py diagnose --help
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py diagnose run 运行编号
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs list
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py jobs show 任务编号
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py make_key --name 服务名 --org-id 组织 --permissions 权限
```

`diagnose` 支持 runs/run/flow/field/stats，查看过程、字段来源与统计。也可用 `/system/console` 和 `/api/system/runs/{run_id}/report`。

`jobs requeue/cancel` 会修改任务，先确认授权对象、环境和范围；重试前查外部动作是否已执行，未知结果不可盲目重复。任务权限限制见 `server/shared/jobs/README.md`。

服务密钥只输出给请求者，配置保存摘要和明确权限；不把明文密钥写到 Git、运行记录或文档。仅生成密钥不代表已完成部署配置。打印环境、报告与示例时不泄露连接秘密或业务数据。
