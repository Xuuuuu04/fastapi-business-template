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

## 多阶段流程

`pipelines list --org 组织` 查看摘要，`pipelines show 编号` 查看阶段运行图和运行记录。
`pipelines resume 编号 --yes` 从当前失败阶段恢复；格式变化需另加 `--accept-schema`，未知外部结果需核实未产生效果后另加 `--confirm-unknown`。普通任务命令不能单独重排或取消流程阶段。

## 隔离端到端演练

演练不读取当前业务库，不继承.env或真实密钥：默认临时SQLite；`--postgres`只在明确授权的隔离库创建随机schema，结束删除本次schema。

```bash
# 独立框架样例，不向产品登记业务（十万行原件）
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py drill --sample --scale 100000 --output var/development/drill
# 产品已登记的Pipeline，清单目录保存上游原始响应和seed JSONL
uv run python ../.agents/skills/fastapi-operations/scripts/run_operations.py drill ../doc/模块/drill_流程.json --output var/development/drill
# 同上增加 --postgres 'postgresql+psycopg://用户:密码@隔离主机/隔离库'
```

配置写法与指标见 [演练说明](../../../server/shared/drills/README.md)。命令按module.py的实际Schedule首入口跑全链；回放没覆盖的请求明确失败，失败/超时返回非零。report.json列阶段耗时、实际提交行数或未知、最慢SQL、采样内存峰值和人工处理需求，artifacts保留发布文件。报告分别列使用原件的阶段、不需要回放的阶段及未完成阶段。模型使用模拟提供者、建表使用登记结构；不能据此说真实模型、生产迁移或外部发布已验证。输出含业务产物，应仅存放在授权本机目录，不提交Git。

## 生成服务密钥

- 明文密钥只显示给请求的人。配置里保存摘要和明确的权限。
- 不要把明文密钥写进 Git、运行记录或文档。
- 生成密钥不等于部署配置已经完成。
- 打印环境信息、报告和示例时，不要带出连接密码或真实业务数据。
