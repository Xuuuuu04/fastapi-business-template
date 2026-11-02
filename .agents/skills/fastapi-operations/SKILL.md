---
name: fastapi-operations
description: 发布上线、查一次运行为什么失败、处理卡住的后台任务或多阶段流程、生成服务密钥时读，命令和步骤都在这里。写业务代码、跑本地检查时不用读。
---

# 发布和运行

| 命令（在 `server/` 执行） | 做什么 |
| --- | --- |
| `uv run dev deploy` | 推送代码，服务器拉取后重新构建并重启服务，等待服务就绪 |
| `uv run dev diagnose run 运行编号` | 看一次运行停在哪一步、为什么 |
| `uv run dev jobs list`、`jobs show 任务编号` | 看后台任务 |
| `uv run dev pipelines list --org 组织`、`pipelines show 编号` | 看多阶段流程 |
| `uv run dev make-key --name 服务名 --org-id 组织 --permissions 权限` | 生成服务密钥 |

`jobs`、`pipelines`、`diagnose run` 连接 `APP_DATABASE_URL` 指定的数据库；执行前先确认该地址属于要查询的环境。

## 发布上线

这里只处理已授权的产品部署。提交 PR、合并代码或发布框架 Release 都不自动授权运行部署命令。

在本机 `main` 分支上执行 `uv run dev deploy`，依次做三件事，哪一步失败就停下报错：

1. `git push` 推当前分支。
2. ssh 到 `DEPLOY_HOST`，在 `DEPLOY_DIR` 里 `git pull`，打印服务器上的提交号，再 `docker compose up -d --build`。compose 先跑迁移，再起接口和 worker。
3. 等 `/health/ready` 返回 ready。

此命令不创建备份，也不自动回滚。要撤回发布，先 `git revert` 后再部署一次；撤回的提交里有数据库迁移的，先另写一个反向迁移。推送后 GitHub Actions 会跑一遍 `dev check`。

第一次部署前手动准备：服务器装好 Docker 和 uv，把仓库 clone 到 `DEPLOY_DIR`，按[运行参考](references/runtime.md)“生产配置”写服务器的 `server/.env`；本机的 `server/.env` 写 `DEPLOY_HOST`（ssh 能连上的主机）和 `DEPLOY_DIR`。

## 在生产上运行 dev 命令

生产镜像里没有开发工具。要查询生产库的任务或重新排队，ssh 到服务器后：

```bash
cd $DEPLOY_DIR/server
uv sync
APP_DATABASE_URL=postgresql+psycopg://app:数据库密码@127.0.0.1:5432/app uv run dev jobs list
```

数据库端口只绑定在服务器的 `127.0.0.1:5432`，外面连不上。

## 查一次运行

起点是错误响应里的 `run_id`，或响应头的 `X-Run-ID`。`dev diagnose run 运行编号` 显示各层操作的调用关系，以及运行停在哪一步；`diagnose` 还有 `runs`（列表）、`flow`（声明的步骤图）、`field`（字段来源）、`stats`（统计）、`budgets`（查询额度）。生产上用系统接口一层层查，见[运行参考](references/runtime.md)“用系统接口查一次运行”。

## 处理后台任务和多阶段流程

- `jobs list`、`jobs show`、`pipelines list`、`pipelines show` 只读。
- `jobs requeue 编号 --yes` 重新排队，`jobs cancel 编号 --yes` 取消还没开始的任务。重新排队前先查外部动作是否已经执行，结果不明时不要直接重新排队，否则可能重复执行（比如重复扣款）。
- 模块升了 `version` 后，已排队的旧版本任务会停下，确认能按新版本跑后用 `jobs requeue 编号 --accept-version --yes`。
- `pipelines resume 编号 --yes` 从失败的阶段继续；数据格式变了加 `--accept-schema`，外部结果未知时先核实没有产生实际效果，再加 `--confirm-unknown`。流程里的单个阶段不能用 `jobs` 命令单独重排或取消。

## 生成服务密钥

`uv run dev make-key` 只显示一次完整密钥，并输出一段配置。完整密钥只交给使用者，配置放进 `APP_API_KEYS`（只存摘要和权限范围）。完整密钥不写进 Git、运行记录或文档。
