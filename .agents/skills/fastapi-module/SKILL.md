---
name: fastapi-module
description: 在本项目新建或修改业务代码（业务包、操作、步骤、存储、后台任务、多阶段流程、路由）时先读并照做，本项目每种写法只有这里这一种。只查业务含义、只跑检查、只做发布时不用读。
---

# 写业务代码

## 开发风格

- 一项业务先从入口到保存整条打通、能检查，再补细节。不要先把底层全做完再往上搭。
- 只有一种写法：用生成命令建包和操作，框架能力只从 `shared.public` 拿，照本 Skill 和[框架用法](references/framework.md)写。不复制别的包改名，不绕开框架另写一套。
- 不写注释和文档字符串。意图用名字、类型、`meaning()` 和测试说清楚，修改原因写进提交说明。
- 不写防御性代码：不加兜底默认值，不接住错误，不做备份和指纹，不为旧版本留兼容分支。出错按下面“出错怎么办”报出来。
- 业务规则没定的先问用户。确认后先写成测试样例，再实现。

## 包分三种

| 类型 | 负责什么 | 能调用谁 | 位置 |
| --- | --- | --- | --- |
| 能力包 `capability` | 拥有自己的表和规则 | 本包；别的能力包只能读，并写进 `read_dependencies` | `service/`，必须有 `store/` |
| 流程包 `workflow` | 把几个能力包串成一条业务链 | 只能调能力包 | `service/`，没有 `store/`，不建表 |
| 工具包 | 纯计算 | 只用自己和标准库 | `library/` |

谁都不能调用流程包，流程包只由入口（HTTP 接口、定时、后台任务）调用。拆包先看数据：一张表只属于一个能力包；要把几个能力包串起来，再建流程包。包里操作多了，流程和数据可以拆成 `flow_主题.py`、`data_主题.py`。

## 生成命令

在 `server/` 执行。`new-operation`、`new-pipeline`、`new-library` 加 `--preview` 只看会改哪些文件、不写入。

| 命令 | 做什么 |
| --- | --- |
| `uv run dev new-module customer_contact --title 客户联系人` | 新建能力包，带示例表、读写操作、测试和 HTTP 入口 |
| `uv run dev new-module order_sync --title 订单同步 --kind workflow` | 新建空的流程包 |
| `uv run dev new-module user_access --title 账号登录 --preset access` | 新建账号登录包，接口固定在 `/api/v1/access`，见[前后端接口](references/frontend-interface.md) |
| `uv run dev new-operation customer_contact normalize_text --title 整理文本 --http` | 给包加一个操作，`--http` 同时生成路由 |
| `uv run dev new-pipeline customer_contact daily --title 每日流程 --stages select,collect,wait,publish --wait wait` | 搭一条多阶段流程，含阶段操作、Wait、后台计划和首阶段定时 |
| `uv run dev new-library text_tools --title 文本工具` | 新建纯工具包 |

- 生成器不更新 `doc/api/openapi.json`。加了接口以后，运行 `uv run dev docs` 更新它。
- 生成的步骤带 `placeholder=True`，换成真实实现后删掉这个标记；`dev check --delivery` 不放过占位步骤。
- 每个新操作带一个正常样例和一个规则异常样例，预期值要换成和用户确认过的业务样例。
- 工具包的 `module.json` 列出 `exports`，和 `public.py` 的 `__all__` 一致；加函数时两处一起改。
- 新增数据表：先 `uv run alembic upgrade head`，再 `uv run alembic revision --autogenerate -m "说明"`，人工看一遍生成的迁移。已有数据库的迁移历史不改。

## 包里放什么

| 位置 | 放什么 |
| --- | --- |
| `public.py` | 对外公开的操作，别的包只能从这里导入 |
| `data.py` | 输入、流程中间数据、返回结果的数据模型，每个字段写 `meaning()` |
| `flow.py` | 各步骤怎样连成一个流程 |
| `steps/` | 每个步骤一件事，声明自己读写哪些字段 |
| `calc/` | 可选，只接收参数、返回结果的纯函数 |
| `store/` | `contract.py` 声明存储方法，`sql.py` 实现，`tables.py` 定义表；SQL 只写在这里 |
| `module.py` | 登记操作、表、后台任务、定时和多阶段流程 |
| `module.json` | 包的类型 `kind`，和 `Module(kind=...)` 一致，改类型两处一起改 |
| `prompts/` | 可选，大模型提示词 |

包内依赖方向：步骤可以用 calc、data、其他步骤和 `store.contract`；store 只用 store 和 calc；calc 只用本包 calc、纯计算的标准库和 `shared.public` 的纯数据和错误类型。需要时间、随机值或外部数据时，由步骤取得后传给 calc，并在步骤上登记 `@step(..., calcs=[函数])`。违反方向时启动和检查都直接报错。

## 选哪种执行方式

| 情况 | 用什么 |
| --- | --- |
| 短规则加一次保存，要么全部成功、要么全部回滚 | 普通操作：`Flow("创建联系人", work=Work, result="result", steps=[validate, save])` |
| 固定来源的大批数据，每批可以单独生效 | 分段任务：`JobPlan(parse_rows, segmented=True, repeat_safe=True, cursor=Cursor)`，每批 `checkpoint.advance(...)`，最后 `finish` |
| 采集、等待、汇算、发布各自要独立事务和恢复点 | 多阶段流程：先 `dev new-pipeline` 搭整条链，再逐阶段替换占位实现 |

完整写法和可运行的例子见[框架用法](references/framework.md)。

## 出错怎么办

业务代码（`service/`、`library/`、`app/api/v1/` 和它们的测试）不写 try/except，也不用 `contextlib.suppress`。业务代码只说清楚什么算错，规则不满足时直接 raise，其余交给框架：

| 哪类问题 | 业务代码写什么 | 框架做什么 |
| --- | --- | --- |
| 进来的数据不对 | 在 Data 上写字段类型和限制 | 拦在门口，返回哪个字段不对 |
| 业务规则不满足 | `raise 某个业务错误()`，错误种类决定状态码和能否重试 | 统一回应，记进运行记录 |
| 写入撞上唯一约束 | `db.one(语句, conflict=已存在错误())` 或 `db.change(语句, conflict=...)` | 只把唯一冲突换成这个业务错误，其他数据库错误照常抛出 |
| 同一对象失败太多次要暂停 | 路由里 `run(操作, 输入, limits=(FailureLimit(...),))` | 计数，超限返回 429，成功后清零 |
| 调外部系统失败或超时 | 不管 | 重试、熔断，记下成功、失败还是结果未知 |
| 数据库断开、超时、太忙 | 不管 | 重试、排队 |
| 代码有 bug | 不管 | 直接失败，保留运行记录 |

需要新的处理方式时，加到框架里，不在业务代码里就地接住。

## 参考

- [框架用法](references/framework.md)：声明、存储、错误、后台任务、多阶段流程、外部调用、文件、大模型、权限、缓存、表格、时钟。
- [前后端接口](references/frontend-interface.md)：给前端的约定、账号登录包、改接口时要做什么。
- 生成器用的代码模板在 [assets/templates](assets/templates/)。
