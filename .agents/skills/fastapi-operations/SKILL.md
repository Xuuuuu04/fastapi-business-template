---
name: fastapi-operations
description: 查看运行报告、手动处理后台任务、生成服务密钥时使用。不负责业务迁移，也不代表有发布授权。
---

# 系统操作

在 `server/` 目录执行。这些命令会读取当前 `APP_` 配置指向的数据库，运行前先确认连接的是哪个环境。

```bash
uv run dev diagnose --help
uv run dev diagnose run 运行编号
uv run dev jobs list
uv run dev jobs show 任务编号
uv run dev make-key --name 服务名 --org-id 组织 --permissions 权限
```

## 查运行情况

`diagnose` 有五个子命令：`runs`（运行列表）、`run`（单次运行）、`flow`（流程）、`field`（字段来源）、`stats`（统计）。也可以在浏览器打开 `/system/console`，或访问 `/api/system/runs/{run_id}/report`。

## 处理后台任务

`jobs list` 和 `jobs show` 是只读的。`jobs requeue`（重新排队）和 `jobs cancel`（取消）会修改任务，执行前先确认两件事：

- 授权是否覆盖这个任务、这个环境。
- 重新排队前，先查任务里的外部动作是否已经执行过。结果不明时不要直接重试，否则可能重复执行（比如重复扣款）。

后台任务使用用户权限的限制，见 `server/shared/jobs/README.md`。

## 多阶段流程

`pipelines list --org 组织` 查看摘要，`pipelines show 编号` 查看阶段运行图和运行记录。`pipelines resume 编号 --yes` 从当前失败的阶段恢复；数据格式有变化时需要另加 `--accept-schema`，外部结果未知时需要先核实没有产生实际效果、再另加 `--confirm-unknown`。普通任务命令不能单独重排或取消流程里的某个阶段。

## 隔离端到端演练

演练不读取当前业务库，也不继承 .env 或真实密钥：默认用临时 SQLite；`--postgres` 只在明确授权的隔离库上创建随机 schema，结束时删除本次的 schema。

```bash
# 独立框架样例，不向产品登记业务（十万行原件）
uv run dev drill --sample --scale 100000 --output var/development/drill
# 产品已登记的 Pipeline，清单目录保存上游原始响应和 seed JSONL
uv run dev drill ../doc/模块/drill_流程.json --output var/development/drill
# 同上，增加 --postgres 'postgresql+psycopg://用户:密码@隔离主机/隔离库'
```

配置写法与指标见[演练说明](../../../server/shared/drills/README.md)。命令按 module.py 里实际的 Schedule 首入口跑完整链路；回放没有覆盖到的请求会明确失败，失败或超时返回非零。report.json 列出各阶段耗时、实际提交的行数（或未知）、最慢的 SQL、采样的内存峰值和需要人工处理的地方，artifacts 保留发布的文件。报告会分别列出：使用了原件的阶段、不需要回放的阶段、没有完成的阶段。模型使用模拟提供者，建表使用登记的结构；不能据此说真实模型、生产迁移或外部发布已经验证。输出里包含业务产物，应只存放在授权的本机目录，不提交 Git。

## 生成服务密钥

用上面的 `uv run dev make-key` 生成。

- 明文密钥只显示给请求的人本人。配置里保存摘要和明确的权限范围。
- 不要把明文密钥写进 Git、运行记录或文档。
- 生成了密钥，不等于部署配置已经完成。
- 打印环境信息、报告和示例时，不要带出连接密码或真实业务数据。
