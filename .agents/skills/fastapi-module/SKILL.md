---
name: fastapi-module
description: 在本项目新增业务包，或把已有业务包调整成固定结构时使用，包含生成命令和代码模板。
---

# 业务包开发

## 开工先读业务现状

开工先读 `.agents/records/business-state/模块名.md` 的生成摘要和手写判断，不要先展开同名 JSON。生成部分由命令维护，内容包括：模块、普通和分段任务、流程、定时入口、最近运行、逾期和待确认；手写部分只放业务判断、外部依赖、下一步。未知保持未知；登记或历史成功不等于当前业务验收。

```bash
# 首次生成，或源码/声明变化后重新生成（不读数据库，运行状态未知）
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名
# 有授权且确认当前数据库后，收工时刷新真实观察
uv run python ../.agents/skills/fastapi-project/scripts/run_project.py business_state --module 模块名 --runs
```

收工时先更新手写部分再刷新生成部分，最后跑检查。生成的源码、依赖摘要或声明变了，生成超过 24 小时，或摘要被手改，都会报过期；check 只比较、不刷新。export_docs 会初始化或更新过期的声明状态，但不访问数据库；要实际运行证据另用 `--runs`。记录只在本机，不提交、也不带入模板副本；新代理或新机器首次生成，不能把本机旧观察当成部署状态。

## 第一步：先写业务文档

在 `doc/模块名/needs.md` 写这个业务的用途，在 `rules.md` 写规则、异常和确认样例。业务含义还没定的地方标"待确认"，不要自己补。

## 先搭整条链的模拟骨架

在新项目根目录保存 `skeleton.json`，最小完整规格如下：

```json
{
  "line": "订单",
  "packages": [{
    "name": "order_shipping", "title": "订单运费", "kind": "capability",
    "operations": [{
      "name": "fee", "title": "计算运费", "access": "public", "effect": "query",
      "input": {"quantity": {"type": "int", "meaning": "件数"}},
      "output": {"amount": {"type": "int", "meaning": "运费分"}},
      "cases": ["order_shipping.R-01-C01"]
    }]
  }]
}
```

在 `server/` 执行 `uv run dev skeleton --init --spec ../skeleton.json`，自动生成独立样例和 rules.md，已有文件不覆盖。填写 `doc/order_shipping/cases/order_shipping.R-01-C01.json` 的业务值（如 quantity=2、amount=200）与规则；编号和测试引用已经填好。再运行 `uv run dev skeleton --spec ../skeleton.json --preview`，确认后去掉 `--preview` 生成。

随后 `dev start --package order_shipping --cases R-01-C01` 开任务卡，替换本包模拟步骤并设置 simulated=False，`dev docs` 后 `dev finish --task 编号` 收工。本包必须真实实现，兄弟包仍模拟只提示；整条相关链测试仍必须通过，最终 `dev check --delivery` 才要求全部为真实实现。样例占位不能当作确认业务值。字段、权限、调用和样例出错时，生成之前逐项报告，不留下半个业务包。

流程包在 `calls[].input` 和 `returns` 里用 `input.字段` 或 `包.操作.字段` 写明每个值的来源。生成的调用步骤按被调用的操作命名，例如调用 `order_pricing.quote` 的步骤叫 `fetch_order_pricing_quote`，产出字段叫 `order_pricing_quote`；样例 `observations` 的 `step` 和 `field` 照这个名字填写。三包连接示例见 `server/tests/framework/skeleton_sample.py`，命令与开发说明见 [填空开发](../../../doc/task-development.md)。

## 生成新包

在 `server/` 目录执行：

```bash
# 新建一个业务包
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_module customer_contact --title 客户联系人
# 给已有的旧包补上结构说明
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py adopt_modules
```

- `new_module` 会建立业务包、测试、业务文档和 HTTP 入口，并更新公共登记。不要复制已有的业务包来当新包。
- `adopt_modules` 要求旧包先通过全部结构检查，才会写入结构说明。它不改业务代码。

## 新增操作与流程

```bash
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_operation customer_contact normalize_text --title 整理文本 --http --preview
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_operation customer_contact normalize_text --title 整理文本 --http
uv run python ../.agents/skills/fastapi-module/scripts/run_module.py new_pipeline customer_contact daily --title 每日流程 --stages select,collect,wait,publish --wait wait
```

在已符合标准结构的模块里生成时，会一次登记 public/data/flow/步骤、可选的 HTTP、规则占位和短测试；每个操作默认生成一个正常样例和一个规则异常样例，共用目录夹具。`--preview` 只预览不写入，报告会列出实际会改的源码和文档。普通操作默认保持普通事务；新流程会生成公开阶段、Wait、后台计划、首阶段定时和演练配置。

生成的文本整理规则只是占位，不代表真实业务完成。先改需求、规则和 Data，再补各阶段的实现和样例。旧模块已有基线迁移时，新增操作不需要再建表；新表仍然单独迁移。add_field 暂未提供；字段变更会检查 reads/writes、接口和文档。

## 什么时候用哪一种

- 普通操作：短规则和短保存，必须一起成功或一起回滚。例：`Flow("创建联系人", work=Work, result="result", steps=[validate, save])`；仍然用原来的 saves=True 一次提交，不加 checkpoint。
- 分段提交：固定来源的大批数据，每批可以独立生效。例：`JobPlan(parse_rows, segmented=True, repeat_safe=True, cursor=Cursor)`；保存步骤每 5000 条推进一次 `checkpoint.advance({"after": next_id}, rows=count)`，最后 finish。游标 Data 与范围要明确，不能把正文塞进游标。
- 多阶段：采集、等待、汇算、发布各自需要独立事务和失败恢复。例：`Pipeline("report.daily", "日报", Begin, (Stage("collect", collect), Wait("wait", ready), Stage("sum", aggregate), Stage("publish", publish)))`；在 module.py 登记 pipelines 和各阶段的 provides/jobs、Schedule 首入口。汇算阶段很大时再使用分段，不要在步骤里循环 sleep。

以上是已定义 Data/操作的登记片段，完整独立样例见 server/tests/framework/drill_sample.py。用 new_pipeline 先搭整条链，再逐阶段替换占位实现；真实规模原件回放跑通全链之后，再补局部细节——生成的样例不算业务完成。细节见[步骤与事务](../../../server/shared/flow/README.md)、[后台任务](../../../server/shared/jobs/README.md)。

## 包内的文件分工

| 位置 | 放什么 |
|---|---|
| `steps/` | 连接输入、纯计算、存储约定和业务异常 |
| `calc/` | 可选，只接收参数并返回结果的纯函数 |
| `store/` | 数据库操作和外部动作 |
| `flow.py` | 声明各步骤怎样连接成一个流程 |
| `data.py` | 输入、流程中间数据、返回结果的数据模型 |
| `public.py` | 包对外公开的操作，别的包只能从这里导入 |

字段用 `meaning()` 写含义；步骤声明自己读写哪些字段，并标注对应的规则编号。完整目录见 `server/service/README.md`，步骤与事务的写法见 `server/shared/flow/README.md`。

## 什么时候把计算放进 calc

需要复用或独立测试的金额、文本、汇算等计算，放在可选的 `calc/` 目录；小赋值仍然可以留在步骤里。calc 只接收参数、返回结果；不得访问数据库、网络、文件、时钟和随机数——需要时间、随机值或外部数据时，由步骤取得后传进来。calc 的短测试直接调用函数，不需要 services、settings 或数据库夹具。生成器默认生成纯函数和短测试。

步骤从本包 calc 导入函数，在已有声明上添加 `@step(..., calcs=[normalize_text])`；直接调用但漏了登记、引用了外包的函数或用了异步函数，启动时会报错。经 store 使用的 calc 也要在所属步骤登记。calcs 声明的是可能调用的范围，不强制每次直接执行所有函数。计算图会列出函数源码；运行图保留声明，耗时包含在所属步骤里，是否逐个实际调用不单独追踪，旧记录明确标未知。

包内依赖方向：步骤可以用 calc、data、其他步骤和 store.contract；store 只用 store 和 calc，不导入步骤、data、flow、module 或 public。calc 只用本包 calc、纯计算标准库和 shared.public 的纯数据/异常类型。共享的数据约定应该移到 store.contract，或改成参数传递。calc 的检查是静态约束，不是执行不可信代码的沙箱；反射、动态函数参数、经数据对象访问外部资源，都不能据此宣称运行时已证明纯净。

已有产品的反向依赖默认保持运行，但在启动和 check 时会输出文件和行号的警告以及迁移建议。把计算移进 calc、改成步骤传参、重新导出文档之后，设置 `APP_MODULE_DEPENDENCIES_STRICT=true`，启动和完整检查就都按错误处理。新生成包的 module.json 默认 dependencies=strict，反向导入直接报错；旧包的结构说明不用改。新 calc 目录里的不纯导入或调用会立即报错。旧短操作没有 calc 时写法不变，也没有数据库迁移。

## 开发过程中

- 一项业务需要的几个包，尽早放在同一份代码里一起运行，不要各写各的最后再合。
- 新增数据表：先把隔离数据库升级到当前最新迁移，再生成增量迁移并人工检查。已有数据库的迁移历史不要替换。
- 检查范围：调试用 `--quick --module`，几个包一起改就列多个 `--module`，整批交付用完整检查（见 `fastapi-check`）。
- 源码格式整理、迁移审查之后统一导出文档；收工时更新业务现状的手写部分，按授权用 business_state --runs 刷新生成部分（没有数据库证据就保持未知），最后检查过期。不要手改生成区域。

## 相关

- 迁移旧系统的业务：读 `fastapi-template` 的[迁移参考](../fastapi-template/references/product-migration.md)。
- 前后端接口适配：读[接口参考](references/frontend-interface.md)，以当前OpenAPI及真实接口结果核对字段和权限。
- 生成器使用的代码模板在 [assets/templates](assets/templates/)。
