---
name: fastapi-operations
description: 发布部署、查看运行报告、手动处理后台任务、生成服务密钥时使用。不负责业务迁移。
---

# 系统操作

在 `server/` 目录执行。这些命令会读取当前 `APP_` 配置指向的数据库，运行前先确认连接的是哪个环境。

```bash
uv run dev diagnose --help
uv run dev diagnose run 运行编号
uv run dev jobs list
uv run dev jobs show 任务编号
uv run dev make-key --name 服务名 --org-id 组织 --permissions 权限
uv run dev deploy
```

生产配置、迁移，以及用系统接口一层层查一次运行，见[运行与运维](references/runtime.md)。

## 发布部署

单人开发直接推到主干，不走 PR。`uv run dev deploy` 依次做三件事，哪一步失败就停下报错：

1. `git push` 推当前分支。
2. ssh 到 `DEPLOY_HOST`，在 `DEPLOY_DIR` 里 `git pull`，再 `docker compose up -d --build`；compose 先跑迁移，再起接口和 worker，`APP_CODE_VERSION` 取服务器上的提交号。
3. 等 `/health/ready` 返回 ready，打印上线的提交号。

不备份、不回滚；要撤回就 `git revert` 后再部署一次。服务器第一次部署前手动做好：装 Docker，clone 仓库到 `DEPLOY_DIR`，在 `server/.env` 写生产配置（见[运行与运维](references/runtime.md)“生产配置”）。本机 `server/.env` 写 `DEPLOY_HOST`（ssh 能连上的主机）和 `DEPLOY_DIR`。

## 查运行情况

`diagnose` 有六个子命令：`runs`（运行列表）、`run`（单次运行）、`flow`（流程）、`field`（字段来源）、`stats`（统计）、`budgets`（查询额度）。也可以在浏览器打开 `/system/console`，或访问 `/api/system/runs/{run_id}/report`。

## 处理后台任务

`jobs list` 和 `jobs show` 是只读的。`jobs requeue`（重新排队）和 `jobs cancel`（取消）会修改任务，执行前先确认两件事：

- 授权是否覆盖这个任务、这个环境。
- 重新排队前，先查任务里的外部动作是否已经执行过。结果不明时不要直接重试，否则可能重复执行（比如重复扣款）。

后台任务使用用户权限的限制，见 fastapi-module 的[框架用法](../fastapi-module/references/framework.md)“后台任务”一节。

## 多阶段流程

`pipelines list --org 组织` 查看摘要，`pipelines show 编号` 查看阶段运行图和运行记录。`pipelines resume 编号 --yes` 从当前失败的阶段恢复；数据格式有变化时需要另加 `--accept-schema`，外部结果未知时需要先核实没有产生实际效果、再另加 `--confirm-unknown`。普通任务命令不能单独重排或取消流程里的某个阶段。

## 生成服务密钥

用上面的 `uv run dev make-key` 生成。

- 明文密钥只显示给请求的人本人。配置里保存摘要和明确的权限范围。
- 不要把明文密钥写进 Git、运行记录或文档。
- 生成了密钥，不等于部署配置已经完成。
- 打印环境信息、报告和示例时，不要带出连接密码或真实业务数据。
