# FastAPI 单体后端模板 3.0.0

这是空业务模板，`MODULES=[]`；产品通过自己的 `app/product.py` 组装。业务实现放 `server/service/`，纯工具放 `server/library/`，共享框架放 `server/shared/`，HTTP 与启动放 `server/app/`。

## 怎么运行

在 `server/` 执行：

```bash
uv sync --locked
uv run dev inspect
uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log
```

首次启动按 `.env.example` 填配置；已有 `.env` 不覆盖。新库执行 `uv run alembic upgrade head`；旧库保留迁移历史，先读升级说明。

## 按任务找入口

| 任务 | Skill |
| --- | --- |
| 入门、开发约定、运行 | [guide](.agents/skills/fastapi-guide/SKILL.md) |
| 包、工具、操作、流程、前后端接口 | [module](.agents/skills/fastapi-module/SKILL.md) |
| 项目图、规则、任务、文档、面板、分支整合 | [project](.agents/skills/fastapi-project/SKILL.md) |
| 分层、双库、当前源码与完整检查 | [check](.agents/skills/fastapi-check/SKILL.md) |
| 运行报告、任务恢复、回放和部署 | [operations](.agents/skills/fastapi-operations/SKILL.md) |
| 新项目、框架升级、旧业务迁移 | [template](.agents/skills/fastapi-template/SKILL.md) |

以上是六个日常 Skill 入口。`fastapi-docs`、`fastapi-migration` 目录保留兼容脚本命名空间，说明已并入 project、module 和 template 的参考，不再提供独立 SKILL.md；复制和升级仍保留这些脚本。

日常执行 `uv run dev start --package 包 --cases 样例`、`uv run dev check --module 包`、`uv run dev finish --task 编号`。整合与交付按 check Skill 做当前源码完整双库检查；沿用记录不能代替本次验收。

## 长期约定

- 先确认规则与独立样例，再实现；推定、采纳、明确确认分别记录。默认一个代理负责到底。
- 能力包负责存取，流程包负责业务链，工具包只做纯计算；包间调用公开操作，SQL 只放存储，步骤声明读写字段。
- 公共框架和开发工具由 `server/framework.lock` 保护；确需修改时说明用途、影响和验证，审查后更新摘要，不降低检查阈值。
- 文档入口是 [doc/README.md](doc/README.md)；开工先读本机业务现状摘要。手写判断与生成段分开，检查和业务验收分开。
- 凭据或权限不够时停下说明，不搜索其他凭据。生产写入、外部动作和切换按实际授权处理。
- 本机证据在 `server/var/development/`，任务与来源在 `.agents/records/`，离线面板在 `out/panel/`；它们不提交、不复制进新产品。

<!-- fastapi-current-state:begin -->
## 当前状态（登记生成）

下面是系统里登记了哪些模块。登记只说明代码里有了它，不代表业务已经完成；
实际运行情况看业务现状档案，或用 project --summary 查询。

- 当前还没有业务模块。新建模块后，这里会自动出现它的登记情况。

想看细节：project --module 模块名 --summary；project --operation 完整操作名。
<!-- fastapi-current-state:end -->
