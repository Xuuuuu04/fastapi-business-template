---
name: fastapi-operations
description: 部署服务、用运行编号定位失败步骤、处理卡住的后台任务或多阶段流程、或签发服务密钥时读。写业务代码或跑本地测试时不用读。
---

# 发布和运行

在确认影响范围后安全部署、定位线上失败位置并处置后台任务，防止造成无法撤销的重复执行。

## 操作步骤

1. **选准环境并核对 `APP_DATABASE_URL`**。所有命令在 `server/` 目录执行（生产容器需先 ssh 到服务器 `cd $DEPLOY_DIR/server` 并确认本地 `127.0.0.1:5432` 库地址），确认连接的是目标环境后再操作：

| 命令 | 做什么 |
| --- | --- |
| `uv run dev deploy` | 推送主干并在服务器拉取构建、等待就绪 |
| `uv run dev diagnose run 运行编号` | 查看指定运行停在哪一步及原因 |
| `uv run dev jobs list`、`jobs show 编号` | 只读查询后台任务列表与详情 |
| `uv run dev pipelines list --org 组织`、`pipelines show 编号` | 只读查询多阶段流程状态 |
| `uv run dev make-key --name 服务名 --org-id 组织 --permissions 权限` | 生成并输出只显示一次的服务密钥配置 |

2. **收到部署授权后发布版本**。在本地 `main` 分支运行 `uv run dev deploy`，该命令会依次执行 `git push`、ssh 拉取并 `docker compose up -d --build`、等待 `/health/ready` 就绪。推送后 GitHub Actions 会自动运行 `dev check --delivery` 和 PostgreSQL 测试；需要回滚时先用 `git revert` 并补写反向迁移再重新部署。
3. **顺着 `run_id` 排查故障位置**。从报错正文或响应头 `X-Run-ID` 拿到运行编号，运行 `uv run dev diagnose run 编号` 对照步骤调用链定位停靠点；在线上无开发工具时，改用[运行参考](references/runtime.md)中的只读 `/api/system/` 接口或访问 `/system/console` 运行排查台。
4. **先核实外部结果再处置卡住的任务或流程**。只读查询命令不改动任何状态；需要干预时按以下规则操作：
   - **重新排队或取消普通任务**：先查明外部接口是否已经执行，确认不会造成重复扣款或重复发送后，执行 `uv run dev jobs requeue 编号 --yes` 或 `cancel`；若模块升级了 `version`，核对兼容性后加 `--accept-version`。
   - **恢复暂停的多阶段流程**：执行 `uv run dev pipelines resume 编号 --yes`（格式变动加 `--accept-schema`，外部结果未知且已核实未生效时加 `--confirm-unknown`），禁止直接用 `jobs` 命令单独取消或重排流程中的某一个阶段。
5. **妥善保管签发的服务密钥**。运行 `uv run dev make-key` 后，完整密钥只交付使用方，配置片段（仅含摘要和权限）写入环境变量 `APP_API_KEYS`，不要将完整密钥写入 Git、运行记录或文档。

## 验收

部署后 `/health/ready` 返回正常且无运行中的报错增量；干预任务或流程后，确认状态已按预期推进且未产生重复外部请求。更多配置与端口细则见[运行参考](references/runtime.md)。
