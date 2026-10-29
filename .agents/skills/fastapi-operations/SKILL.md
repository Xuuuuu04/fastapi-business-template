---
name: fastapi-operations
description: 发布上线、查一次运行为什么失败、处理卡住的后台任务或多阶段流程、生成服务密钥时读，命令和步骤都在这里。写业务代码看 fastapi-module；本地检查看 fastapi-check。
---

# 发布和运行

命令在 `server/` 执行。除 `deploy` 外，命令读取当前 `APP_` 配置指向的数据库，先确认连的是哪个环境。

| 命令 | 做什么 |
| --- | --- |
| `uv run dev deploy` | 推送代码，服务器拉取后重建重启，等到服务就绪 |
| `uv run dev diagnose run 运行编号` | 看一次运行停在哪一步、为什么 |
| `uv run dev jobs list`、`jobs show 任务编号` | 看后台任务 |
| `uv run dev pipelines list --org 组织`、`pipelines show 编号` | 看多阶段流程 |
| `uv run dev make-key --name 服务名 --org-id 组织 --permissions 权限` | 生成服务密钥 |

## 发布上线

单人开发直接推主干，不走 PR。`uv run dev deploy` 依次做三件事，哪一步失败就停下报错：

1. `git push` 推当前分支。
2. ssh 到 `DEPLOY_HOST`，在 `DEPLOY_DIR` 里 `git pull`，再 `docker compose up -d --build`。compose 先跑迁移，再起接口和 worker；`APP_CODE_VERSION` 取服务器上的提交号。
3. 等 `/health/ready` 返回 ready，打印上线的提交号。

不备份、不回滚，要撤回就 `git revert` 后再部署一次。

第一次部署前手动准备：服务器装好 Docker，把仓库 clone 到 `DEPLOY_DIR`，在服务器的 `server/.env` 写生产配置（见[运行参考](references/runtime.md)“生产配置”）；本机的 `server/.env` 写 `DEPLOY_HOST`（ssh 能连上的主机）和 `DEPLOY_DIR`。

## 查一次运行

起点是错误响应里的 `run_id`，或响应头的 `X-Run-ID`。`uv run dev diagnose run 运行编号` 给出调用树和停在哪一步；`diagnose` 还有 `runs`（列表）、`flow`（声明的步骤图）、`field`（字段来源）、`stats`（统计）、`budgets`（查询额度）。也可以开 `/system/console`，或按[运行参考](references/runtime.md)里的系统接口一层层查。

## 处理后台任务和多阶段流程

- `jobs list`、`jobs show`、`pipelines list`、`pipelines show` 只读。
- `jobs requeue`（重新排队）和 `jobs cancel`（取消还没开始的任务）会改任务。重新排队前先查任务里的外部动作是否已经执行过，结果不明的不要直接重排，否则可能重复执行（比如重复扣款）。
- `pipelines resume 编号 --yes` 从失败的阶段继续；数据格式变了加 `--accept-schema`，外部结果未知时先核实没有产生实际效果，再加 `--confirm-unknown`。流程里的单个阶段不能用 `jobs` 命令单独重排或取消。

## 生成服务密钥

`uv run dev make-key` 输出一次明文和一段配置。明文只交给要用它的人，配置放进 `APP_API_KEYS`（只存摘要和权限范围）。明文不写进 Git、运行记录或文档。
