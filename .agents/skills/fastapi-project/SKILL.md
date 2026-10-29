---
name: fastapi-project
description: 定位代码、查看改动影响、本机整合分支和保留检查证据时使用。
---

# 定位、影响与整合

以下命令在 `server/` 执行，只读本机声明，不连接数据库。

- `uv run dev locate --query 业务词`：按模块、操作、字段、步骤、接口路径查找，返回源码位置和下一步命令。
- `uv run dev impact --base origin/main`：列出改动涉及的框架文件、模块、接口变化、迁移和建议检查范围。建议的检查命令还没执行，不能当作通过。
- `uv run dev docs`：从当前声明重新生成 `doc/api/openapi.json`，`--check` 只比较不写入。这是给前端和 compare-api 用的接口契约，项目不再生成其他文档。

## 整合分支

在干净的命名分支上执行 `uv run dev merge 分支 --postgres 隔离测试控制连接`。它在本机临时工作树中整合，重新生成模块登记、路由和 openapi.json，验证增量多头迁移与全新建库，再跑完整双库检查。普通源码或系统路由冲突时停止，保留阶段报告与工作树，原分支不改。`--preview` 只保留通过检查的候选；成功后再次核对原分支和工作区，快进应用。此命令不推送远程，也不升级生产数据库。

## 保留检查证据

```bash
uv run dev pin 检查编号 --reason "交付验收原件"
uv run dev gc
uv run dev gc --apply --preview-id 本次预览摘要
```

`dev gc` 默认只预览；每份源码与范围最近三轮、所有失败和显式固定的检查都保留。解除固定用 `dev pin 检查编号 --remove`。

运行记录用运维 Skill 的 `dev diagnose` 查看，需要先确认实际数据库和授权。检查通过、合并成功、部署和业务验收分别汇报。
