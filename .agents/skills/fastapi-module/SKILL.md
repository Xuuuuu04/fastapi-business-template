---
name: fastapi-module
description: 在本项目新建或修改业务包、操作、步骤、存储、后台任务、多阶段流程或路由时读。只查业务、只跑检查或只做发布时不用读。
---

# 写业务代码

用统一结构和框架入口编写业务包，跟着已有模式走，让一处只装一件事。

## 编写步骤

1. **先划分包类型与职责**。按数据归属拆包：一张表只归一个能力包；需要串联多个能力包写操作时，再建流程包；纯计算函数放工具包。
2. **用生成命令创建骨架**。在 `server/` 运行下表对应命令生成目录与注册项（`new-operation`、`new-pipeline`、`new-library` 可加 `--preview` 预览），不要手工复制旧包改名：

| 命令 | 用途 |
| --- | --- |
| `uv run dev new-module customer_contact --title 客户联系人` | 新建能力包（含示例表、操作、测试和路由） |
| `uv run dev new-module order_sync --title 订单同步 --kind workflow` | 新建空流程包 |
| `uv run dev new-module user_access --title 账号登录 --preset access` | 新建账号登录包，见[前后端接口](references/frontend-interface.md) |
| `uv run dev new-operation customer_contact normalize_text --title 整理文本 --http` | 新增操作，`--http` 同时生成路由 |
| `uv run dev new-pipeline customer_contact daily --title 每日流程 --stages select,collect,wait,publish --wait wait` | 生成多阶段流程与定时计划 |
| `uv run dev new-library text_tools --title 文本工具` | 新建纯工具包 |

3. **按单向依赖组织包内文件**。框架能力只从 `shared.public` 导入，先实现从入口到保存的完整链路并移除步骤上的 `placeholder=True`；新增表先执行 `uv run alembic upgrade head` 再生成迁移。
4. **选定执行方式并直接抛出错误**。短事务用普通 `Flow`，大批量数据用 `JobPlan(segmented=True)`，跨提交等待用多阶段流程；业务代码不写 `try/except` 或 `suppress`，规则不满足时直接 `raise BusinessError`。
5. **更新接口文档并补齐业务样例**。修改接口后运行 `uv run dev docs` 更新 `doc/api/openapi.json`，把生成测试里的占位样例换成与用户确认过的正常和异常样例。

## 三类包边界

| 类型 | 负责什么 | 能调用谁 | 位置 |
| --- | --- | --- | --- |
| 能力包 `capability` | 拥有自己的表和规则 | 本包操作；跨包只调用其他能力包的 query 操作，并把对方包名写进 `read_dependencies` | `service/`，必须有 `store/` |
| 流程包 `workflow` | 把几个能力包串成业务链 | 只能调用能力包 | `service/`，没有 `store/`，不建表 |
| 工具包 `library` | 无副作用纯计算 | 只用本包和标准库 | `library/`，修改包类型时两处一起改 |

## 包内结构与依赖方向

| 文件或目录 | 职责 | 允许导入的范围 |
| --- | --- | --- |
| `public.py` | 对外公开操作与数据 | 供外部包导入的唯一入口 |
| `data.py` | 数据模型，每个字段写 `meaning()` | `shared.public` |
| `flow.py` | 编排步骤顺序与分支条件 | 本包 `data`、`steps` 与依赖的 `public` |
| `steps/` | 读写声明与单一动作实现 | 本包 `calc`、`data`、其他步骤与 `store/contract.py` |
| `calc/` | 只收参并返回结果的纯函数 | 本包 `calc`、标准库、`shared.public` 纯数据与错误 |
| `store/` | 定义表与 SQLAlchemy Core 查询 | 仅 `store` 与本包 `calc`（禁止直接导出 `sql.py`） |
| `module.py`、`module.json` | 登记表、操作、任务和远程依赖 | 类型 `kind` 在 `module.py` 与 `module.json` 保持一致 |

## 异常处理分工

| 场景 | 业务代码写法 | 框架处理方式 |
| --- | --- | --- |
| 输入格式或范围错 | 在 `Data` 字段写类型与限制 | 执行前拦截并返回问题字段 |
| 业务规则不通过 | 直接 `raise` 自定义 `BusinessError` | 返回对应状态码并记入运行记录 |
| 唯一约束冲突 | `db.one(..., conflict=错误())` 或 `db.change(..., conflict=...)` | 只把唯一冲突转为该业务错误 |
| 高频失败限制 | 路由中写 `run(..., limits=(FailureLimit(...),))` | 超限返回 429，成功后清零 |

## 验收与参考

运行 `uv run dev check --module 包名` 通过且无 `placeholder=True` 残留；详细声明见[框架用法](references/framework.md)、[前后端接口](references/frontend-interface.md)和 [assets/templates](assets/templates/)。
