---
name: fastapi-check
description: 改完代码要验证、准备提交、或检查与测试报错时读，用来选定检查范围、真跑操作并核对报告。发布或查线上运行时不用读。
---

# 检查和测试

运行静态检查、真跑操作与分层测试，让每次改动的结果和问题位置看得见、可核对。

## 执行步骤

1. **按改动范围选命令检查**。在 `server/` 目录从最小范围开始检查，改了公共代码或准备提交前跑完整检查（发现不合规先修代码，不放宽阈值）：

| 场景 | 命令 |
| --- | --- |
| 调试单个包（跳过类型和文档） | `uv run dev check --quick --module 包` |
| 验证指定业务包 | `uv run dev check --module A --module B` |
| 按主干差异自动选包 | `uv run dev check --affected --base origin/main` |
| 改框架或批量提交前 | `uv run dev check`（可用 `--group pure` 等分组） |
| 交付前终检（拦截占位与模拟步骤） | `uv run dev check --delivery` |
| 验证 PostgreSQL 锁与数值精确性 | 任一检查加 `--postgres 测试库地址` |

2. **真实执行一次操作核对运行报告**。在本地 `.env` 指向的可重置开发库跑通 `alembic upgrade head` 后，执行 `dev run` 检查每一步输入输出与报错：

   ```bash
   uv run dev run customer_contact.create_contact --input '{"name": "张三"}' --allow-write
   uv run dev run --case tests/modules/包/cases/名称.json --allow-write
   ```

   需要反复核对的场景把样例（不含真实凭据）存成 `.json` 用 `--case` 复跑；写操作必须加 `--allow-write`。
3. **核对报错报告与代码规则**。测试或检查失败时先读报错输出的中文运行报告（完整 JSON 在 `server/var/development/failures/`），再对照下表修改源码：

| 规则名 | 检查要求 |
| --- | --- |
| `comment`、`docstring` | 删除普通注释和文档字符串 |
| `catch` | 业务代码不用 `try/except` 或 `suppress` |
| `file_lines`、`function_lines`、`nesting` | 文件不超过 300 行、函数不超过 50 行、嵌套不超过 4 层 |
| `blocking_call` | 异步函数里禁止调用同步阻塞接口 |
| `module_name`、`name_format`、`name_vague`、`step_name`、`condition_name` | 避免含糊命名（如 `utils`、`helper`），遵守前缀格式 |
| `not_listed`、`missing_module`、`not_exposed`、`unused` | 模块、入口与路由登记保持一致；非入口操作写 `entry=False` |
| `import_*` | 遵守跨包和包内单向依赖方向 |
| `calc_dependency`、`calc_purity` | `calc` 禁止读取外部状态或产生副作用 |
| `library_layout`、`library_exports`、`library_declaration` | 工具包结构、`exports` 和 `__all__` 保持一致 |
| `tools` | `--delivery` 模式下禁止保留占位或模拟步骤 |
| `unused_exception` | 清理 `rules.py` 里已经用不上的例外项 |
| `writing_style` | 根文档、PR 模板和 Skill 文档中不使用禁用黑话和生硬句式 |

4. **改完接口要同步更新文档**。执行 `uv run dev docs` 更新 `doc/api/openapi.json`；需要复用的新开发工具放进对应 Skill 的 `scripts/` 并登记在 `server/devtools/src/fastapi_dev/main.py` 的 `COMMANDS` 中。
5. **按改动涉及的风险加跑专项检查**：
   - 改了任务领取或超时接管逻辑时跑 `uv run dev verify-model`（详见[任务状态模型](references/job-model.md)）。
   - 需要启动隔离 HTTP 服务供前端浏览器联调时跑 `uv run dev acceptance-server --port 0 --run-id 本轮编号`（详见[前后端验收](references/acceptance.md)）。
   - 单元测试与契约测试写法见[测试说明](references/tests.md)。

## 验收与产出

汇报检查结论时，分开写清实际运行了单包检查、全仓检查、PostgreSQL 测试、状态模型检查还是前后端隔离验收；CI 在 `push` 与 `pull_request` 时运行 `dev check --delivery` 与 PostgreSQL 全量测试，PR 需要全部通过并按模板写清业务规则与测试映射。
