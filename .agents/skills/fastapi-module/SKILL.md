---
name: fastapi-module
description: 在本项目新增业务包，或把已有业务包调整成固定结构时使用，包含生成命令和代码模板。
---

# 业务包开发

## 开工先读业务现状

先读 `.agents/records/business-state/模块名.md` 的生成摘要和手写判断，不先展开同名JSON。生成部分由命令维护：模块、普通/分段任务、流程、定时入口、最近运行、逾期与待确认；手写部分只放业务判断、外部依赖、下一步。未知保持未知，登记或历史成功不等于当前业务验收。

```bash
# 首次或源码/声明变化后生成（不读数据库，运行状态未知）
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名
# 有授权且确认当前数据库后，收工刷新真实观察
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名 --runs
```

收工更新手写部分并刷新生成部分，再检查。生成源码/依赖摘要或声明变了、生成超过24小时、摘要被手改都会报过期；check只比较不刷新。export_docs会初始化/更新过期的声明状态，不访问数据库；要实际运行证据另用--runs。记录只在本机，不提交或带入模板副本；新代理/新机器首次生成，不能把本机旧观察当部署状态。

## 第一步：先写业务文档

在 `doc/模块名/needs.md` 写这个业务的用途，在 `rules.md` 写规则、异常和确认样例。业务含义还没定的地方标"待确认"，不要自己补。

## 生成新包

在 `server/` 执行：

```bash
# 新建一个业务包
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_module customer_contact --title 客户联系人
# 给已有的旧包补上结构说明
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py adopt_modules
```

- `new_module` 会建立业务包、测试、业务文档和 HTTP 入口，并更新公共登记。不要复制已有的业务包来当新包。
- `adopt_modules` 要求旧包已通过全部结构检查，才会写入结构说明。它不改业务代码。

## 新增操作与流程

```bash
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_operation customer_contact normalize_text --title 整理文本 --http --preview
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_operation customer_contact normalize_text --title 整理文本 --http
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_pipeline customer_contact daily --title 每日流程 --stages select,collect,wait,publish --wait wait
```

在已有标准模块生成，一次登记public/data/flow/步骤、可选HTTP、规则占位及短测试；各操作默认一个正常和一个规则异常，共用目录夹具。预览不写，报告列实际源码和文档改动。普通操作默认保持普通事务；新流程生成公开阶段、Wait、后台计划、首阶段定时及演练配置。

生成的文本整理规则只作为占位，不代表真实业务完成。先改需求/规则和Data，再补各阶段实现和样例。旧模块已有基线迁移时，新增操作不需要再建表；新表仍单独迁移。add_field暂未提供，字段变更检查reads/writes/接口和文档。

## 什么时候用哪一种

- 普通操作：短规则和短保存，必须一起成功/回滚。例：`Flow("创建联系人", work=Work, result="result", steps=[validate, save])`；仍用原saves=True一次提交，不加checkpoint。
- 分段提交：固定来源的大批数据，每批可以独立生效。例：`JobPlan(parse_rows, segmented=True, repeat_safe=True, cursor=Cursor)`；保存步骤每5000条推进`checkpoint.advance({"after": next_id}, rows=count)`，最后finish。游标Data与范围明确，不能把正文塞进游标。
- 多阶段：采集→等待→汇算→发布需要各自事务和失败恢复。例：`Pipeline("report.daily", "日报", Begin, (Stage("collect", collect), Wait("wait", ready), Stage("sum", aggregate), Stage("publish", publish)))`；module.py登记pipelines与各阶段provides/jobs、Schedule首入口。汇算阶段很大时再使用分段，不在步骤里循环sleep。

以上为已定义Data/操作的登记片段，完整独立样例见server/tests/framework/drill_sample.py。用new_pipeline先搭整链，再逐阶段替换占位实现；真实规模原件回放全链成功后补局部细节，生成样例不是业务完成。细节见[flow](../../../server/shared/flow/README.md)、[jobs](../../../server/shared/jobs/README.md)。

## 包内的文件分工

| 位置 | 放什么 |
|---|---|
| `steps/` | 连接输入、纯计算、存储约定和业务异常 |
| `calc/` | 可选，接收参数并返回结果的纯函数 |
| `store/` | 数据库操作和外部动作 |
| `flow.py` | 声明各步骤怎样连接成一个流程 |
| `data.py` | 输入、流程中间数据、返回结果的数据模型 |
| `public.py` | 包对外公开的操作，别的包只能从这里导入 |

字段用 `meaning()` 写含义；步骤声明读写哪些字段，并标注对应的规则编号。完整目录见 `server/service/README.md`，步骤与事务写法见 `server/shared/flow/README.md`。


## 什么时候把计算放进 calc

需要复用或独立测试的金额、文本、汇算等计算放在可选 `calc/`，小赋值仍可留在步骤里。calc 只接收参数、返回结果；不得访问数据库、网络、文件、时钟和随机数。需要时间、随机值或外部数据，由步骤取得后传入；calc 的短测试直接调用函数，无需 services、settings 或数据库夹具。生成器默认生成纯函数和短测试。

步骤从本包 calc 导入函数，在已有声明添加 `@step(..., calcs=[normalize_text])`；直接调用漏登记、引用外包或异步函数启动时报错。经 store 使用的 calc 也在所属步骤登记。calcs 是可能调用的范围，不强制每次直接执行所有函数。计算图列出函数源码；运行图保留声明，耗时包含在所属步骤，是否逐个实际调用不单独追踪，旧记录明确未知。

包内方向：steps 可用 calc、data、其他步骤与 store.contract；store 只用 store 和 calc，不导入步骤、data、flow、module 或 public。calc 只用本包 calc、纯计算标准库及 shared.public 的纯数据/异常类型。共享的数据约定应移到 store.contract 或由参数传递。calc 的检查是静态约束，不是执行不可信代码的沙箱；反射、动态函数参数以及经数据对象访问外部资源不能据此宣称运行时已证明纯净。

已有产品反向依赖默认在启动和 check 输出文件:行号警告及迁移建议，保持运行。移计算到 calc、改为步骤传参，并重新导出文档；完成后设置 `APP_MODULE_DEPENDENCIES_STRICT=true`，启动和完整检查均按错误处理。新生成包的 module.json 默认 dependencies=strict，反向导入直接报错；旧包结构说明无需改动。新 calc 目录中的不纯导入/调用立即报错。旧短操作无 calc 时写法不变，无数据库迁移。

## 开发过程中

- 一项业务需要的几个包，尽早放在同一份代码里一起运行，不要各写各的最后再合。
- 新增数据表：先把隔离数据库升级到当前最新迁移，再生成增量迁移并人工检查。已有数据库的迁移历史不要替换。
- 检查范围：调试用 `--quick --module`，几个包一起用多个 `--module`，整批交付用完整检查（见 `fastapi-check`）。
- 源码格式整理、迁移审查之后统一导出文档；收工更新业务现状手写部分，按授权使用business_state --runs刷新生成部分（没有DB证据保持未知），最后检查过期。不要手改生成区域。

## 相关

- 迁移旧系统的业务：读 `fastapi-migration`。
- 生成器使用的代码模板在 [assets/templates](assets/templates/)。
