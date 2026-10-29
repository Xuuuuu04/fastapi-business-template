---
name: fastapi-module
description: 在本项目新增业务包，或把已有业务包调整成固定结构时使用，包含生成命令和代码模板。
---

# 业务包开发

## 第一步：先问清业务

业务含义还没定的地方先问用户，不要自己补。

## 包分三种

| 类型 | 负责什么 | 能调用谁 | 目录 |
| --- | --- | --- | --- |
| 能力包 `capability` | 拥有自己的表和规则 | 本包；别的能力包只能读（`read_dependencies`） | `service/`，必须有 `store/` |
| 流程包 `workflow` | 把几个能力包串成业务链 | 只能调能力包，不调其他流程包 | `service/`，不许有 `store/`，不建表 |
| 工具包 | 纯计算 | 只用自己和标准库 | `library/` |

谁都不能调用流程包，流程包只由入口（HTTP 接口、定时、后台任务）调用。拆包先看数据：一张表只属于一个能力包；要把几个能力包串起来，再建流程包。包里操作多了，流程和数据可以拆成 `flow_主题.py`、`data_主题.py`。

## 生成新包

在 `server/` 目录执行：

```bash
# 新建能力包（带示例表和读写操作）
uv run dev new-module customer_contact --title 客户联系人
# 新建流程包（空包，再用 new-operation 加操作）
uv run dev new-module order_sync --title 订单同步 --kind workflow
# 给已有的旧包补上结构说明
uv run dev adopt-modules
```

- `new-module` 会建立业务包、测试和 HTTP 入口，并更新公共登记。不要复制已有的业务包来当新包。
- `adopt-modules` 要求旧包先通过全部结构检查，才会写入结构说明。它不改业务代码。
- 需要账号登录时加 `--preset access`，例如 `uv run dev new-module user_access --title 账号登录 --preset access`：生成登录、新建账号、账号表迁移、文档和测试，接口路径固定为 `/api/v1/access`，与前端模板的登录约定一致，见[接口参考](references/frontend-interface.md)。

## 新增操作与流程

```bash
uv run dev new-operation customer_contact normalize_text --title 整理文本 --http --preview
uv run dev new-operation customer_contact normalize_text --title 整理文本 --http
uv run dev new-pipeline customer_contact daily --title 每日流程 --stages select,collect,wait,publish --wait wait
```

在已符合标准结构的模块里生成时，会一次登记 public/data/flow/步骤、可选的 HTTP、规则占位和短测试；每个操作默认生成一个正常样例和一个规则异常样例，共用目录夹具。`--preview` 只预览不写入，报告会列出实际会改的源码和文档。普通操作默认保持普通事务；新流程会生成公开阶段、Wait、后台计划和首阶段定时。

生成的文本整理规则只是占位，不代表真实业务完成。先改需求、规则和 Data，再补各阶段的实现和样例。旧模块已有基线迁移时，新增操作不需要再建表；新表仍然单独迁移。add_field 暂未提供；字段变更会检查 reads/writes、接口和文档。

## 什么时候用哪一种

- 普通操作：短规则和短保存，必须一起成功或一起回滚。例：`Flow("创建联系人", work=Work, result="result", steps=[validate, save])`；仍然用原来的 saves=True 一次提交，不加 checkpoint。
- 分段提交：固定来源的大批数据，每批可以独立生效。例：`JobPlan(parse_rows, segmented=True, repeat_safe=True, cursor=Cursor)`；保存步骤每 5000 条推进一次 `checkpoint.advance({"after": next_id}, rows=count)`，最后 finish。游标 Data 与范围要明确，不能把正文塞进游标。
- 多阶段：采集、等待、汇算、发布各自需要独立事务和失败恢复。例：`Pipeline("report.daily", "日报", Begin, (Stage("collect", collect), Wait("wait", ready), Stage("sum", aggregate), Stage("publish", publish)))`；在 module.py 登记 pipelines 和各阶段的 provides/jobs、Schedule 首入口。汇算阶段很大时再使用分段，不要在步骤里循环 sleep。

以上是已定义 Data/操作的登记片段，完整样例见 server/tests/framework/pipeline_sample.py。用 `dev new-pipeline` 先搭整条链，再逐阶段替换占位实现；生成的样例不算业务完成。细节见[框架用法](references/framework.md)。

## 包内的文件分工

| 位置 | 放什么 |
|---|---|
| `steps/` | 连接输入、纯计算、存储约定和业务异常 |
| `calc/` | 可选，只接收参数并返回结果的纯函数 |
| `store/` | 数据库操作和外部动作 |
| `flow.py` | 声明各步骤怎样连接成一个流程 |
| `data.py` | 输入、流程中间数据、返回结果的数据模型 |
| `public.py` | 包对外公开的操作，别的包只能从这里导入 |

字段用 `meaning()` 写含义；步骤声明自己读写哪些字段。生成器产出的样例步骤带 `placeholder=True`，换成真实实现后删掉这个标记；`dev check --delivery` 不允许留着占位步骤。各机制的写法见[框架用法](references/framework.md)。

## 什么时候把计算放进 calc

需要复用或独立测试的金额、文本、汇算等计算，放在可选的 `calc/` 目录；小赋值仍然可以留在步骤里。calc 只接收参数、返回结果；不得访问数据库、网络、文件、时钟和随机数；需要时间、随机值或外部数据时，由步骤取得后传进来。calc 的短测试直接调用函数，不需要 services、settings 或数据库夹具。生成器默认生成纯函数和短测试。

步骤从本包 calc 导入函数，在已有声明上添加 `@step(..., calcs=[normalize_text])`；直接调用但漏了登记、引用了外包的函数或用了异步函数，启动时会报错。经 store 使用的 calc 也要在所属步骤登记。calcs 声明的是可能调用的范围，不强制每次直接执行所有函数。计算图会列出函数源码；运行图保留声明，耗时包含在所属步骤里，是否逐个实际调用不单独追踪。

包内依赖方向：步骤可以用 calc、data、其他步骤和 store.contract；store 只用 store 和 calc，不导入步骤、data、flow、module 或 public。calc 只用本包 calc、纯计算标准库和 shared.public 的纯数据/异常类型。共享的数据约定应该移到 store.contract，或改成参数传递。calc 的检查是静态约束，不是执行不可信代码的沙箱；反射、动态函数参数、经数据对象访问外部资源，都不能据此宣称运行时已证明纯净。

违反包内依赖方向、calc 里有不纯的导入或调用，服务启动和检查都直接报错，没有只警告的模式。

## 出了问题怎么办

业务代码（`service/`、`library/`、`app/api/v1/` 和它们的测试）不写 try/except，也不用 `contextlib.suppress`，检查会报 `catch`。业务代码只做两件事：说清楚什么算错，业务规则不满足时直接 raise。其余交给框架：

| 哪类问题 | 业务代码写什么 | 框架做什么 |
| --- | --- | --- |
| 进来的数据不对 | 在 Data 上声明字段类型和限制 | 拦在门口，返回哪个字段不对 |
| 业务规则不满足 | `raise 某个业务错误()`，错误种类决定状态码和能否重试 | 统一回应并记进运行记录 |
| 写入撞上唯一约束 | `db.one(语句, conflict=已存在错误())` 或 `db.change(语句, conflict=...)` | 只把唯一冲突换成声明的业务错误，其他数据库错误照常抛出 |
| 同一对象失败太多次要暂停 | 路由里 `run(操作, 输入, limits=(FailureLimit(...),))` | 计数、超限返回 429、成功后清零 |
| 调外部系统失败、超时 | 不管 | 重试、熔断，记下成功、失败还是结果未知 |
| 数据库断开、超时、太忙 | 不管 | 重试、排队 |
| 代码 bug | 不管 | 直接失败，保留运行记录 |

需要新的处理方式时，加到框架里，不在业务代码里就地接住。

## 开发过程中

- 一项业务需要的几个包，尽早放在同一份代码里一起运行，不要各写各的最后再合。
- 新增数据表：先把隔离数据库升级到当前最新迁移，再生成增量迁移并人工检查。已有数据库的迁移历史不要替换。
- 检查范围：调试用 `--quick --module`，几个包一起改就列多个 `--module`，整批交付用完整检查（见 `fastapi-check`）。
- 源码格式整理、迁移审查之后运行 `uv run dev docs` 更新 openapi.json。

## 相关

- 框架各机制怎么写（声明、存储、错误、后台任务、多阶段流程、外部调用、文件、大模型、权限、缓存、表格、时钟）：读[框架用法](references/framework.md)。
- 迁移旧系统的业务：读 `fastapi-template` 的[迁移参考](../fastapi-template/references/product-migration.md)。
- 前后端接口适配：读[接口参考](references/frontend-interface.md)，以当前OpenAPI及真实接口结果核对字段和权限。
- 生成器使用的代码模板在 [assets/templates](assets/templates/)。
