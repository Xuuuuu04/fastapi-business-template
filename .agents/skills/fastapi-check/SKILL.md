---
name: fastapi-check
description: 改完代码要验证、准备提交、或检查和测试报错时读，按这里选检查范围、真跑一次操作看运行报告、写测试。部署上线、查线上运行时不用读。
---

# 检查和测试

`uv run dev check` 只做两件事：静态检查（风格、格式、类型、接口文档、代码规则）和跑测试。命令在 `server/` 执行。

## 选范围

| 场景 | 命令 |
| --- | --- |
| 调试一个包 | `uv run dev check --quick --module 包` |
| 改了几个包 | `uv run dev check --module A --module B` |
| 按和主干的差异自动选包 | `uv run dev check --affected --base origin/main` |
| 改了框架，或一批改动做完 | `uv run dev check`；`--group pure`（或 module、flow、framework）只跑一组 |
| 交付前 | `uv run dev check --delivery`，额外要求没有占位和模拟步骤 |
| 生产用 PostgreSQL | 任意一条加 `--postgres 测试库地址`，只用专门的测试库 |

从最小范围开始，改了公共代码再跑全部。`--quick` 不跑类型检查和接口文档核对。按包检查时，测试在一个进程里跑，代码规则也只扫这几个包的文件，所以比完整检查快得多；完整检查才开多个进程并行跑测试。

## 真跑一次看结果

检查过了还要亲眼看一次真实运行。用本地 `.env` 的数据库跑一次登记的操作，打印结果和运行报告（每一步读写了什么、调了谁、停在哪）：

```bash
uv run dev run customer_contact.create_contact --input '{"name": "张三"}' --allow-write
uv run dev run customer_contact.create_contact --input-file 样例.json --org north --allow-write
```

只允许 local/test 环境，command 操作必须显式加 `--allow-write`，确认 `.env` 指向专门的开发数据。默认以本地开发者身份运行；`--org` 指定组织。成功退出码 0，失败 1，失败时报告写明停在哪一步、为什么。本地库要先 `uv run alembic upgrade head`。多阶段流程按阶段分别跑。

## 复用样例和扩展工具

优先用 `dev locate` 找代码、`dev diagnose` 查记录、生成器建包、`dev check` 验证。需要反复真跑的业务样例放在 `tests/modules/包/cases/名称.json`，用 `uv run dev run --case 文件路径`；写操作加 `--allow-write`。例如先用 `dev new-operation customer_contact normalize_text --title 整理文本` 生成样例操作，配置只含合成数据，不含凭据：

```json
{"operation":"customer_contact.normalize_text","input":{"text":" 张三 "},"org":"north","permissions":["customer_contact.run"],"expected":{"text":"张三"}}
```

`operation`、`input` 按真实操作填写；`expected` 是用户确认的完整 JSON 结果，金额按接口格式写。错误字段、结果不符、权限不足都返回非零退出码；`expected` 检查发生在操作提交之后，不会回滚，写样例只用于可重置的开发数据。省略 `expected` 只运行、不声称业务验证通过。

- 调整产品优先用 `app/product.py`、现有命令参数和配置；配置只放数据，不执行 Python 或 shell。
- 已有命令能做的事不另写脚本，不用临时 SQL 绕过正式操作、权限和迁移。
- 确需复用的新工具放所属项目 Skill 的 `scripts/`，从 `dev` 明确登记，带参数校验、只读/写入说明、失败退出码和针对性测试，再在该 Skill 记录入口。先核对现有职责，不建万能脚本目录。
- 一次性试验放系统临时目录，只用隔离测试数据；有价值的反例转成回归测试，结束后清理。

## 代码规则

检查报出的规则名和意思：

| 规则 | 意思 |
| --- | --- |
| `comment`、`docstring` | 代码里不写注释和文档字符串 |
| `catch` | 业务代码不写 try/except 和 suppress，写法见 fastapi-module“出错怎么办” |
| `file_lines`、`function_lines`、`nesting` | 文件超过 300 行、函数超过 50 行、嵌套超过 4 层，按用途拆开 |
| `blocking_call` | 异步代码里调用了同步等待 |
| `module_name`、`name_format`、`name_vague`、`step_name`、`condition_name` | 名字格式不对或太含糊（如 utils、helper） |
| `not_listed`、`missing_module`、`not_exposed`、`unused` | 模块登记和实际的包、入口、调用对不上；只给别的操作调用的写 `entry=False` |
| `import_shared`、`import_web`、`import_database`、`import_module`、`import_layer`、`import_library`、`import_relative`、`import_dynamic`、`import_direction` | 导入越界，规则见 fastapi-module“包里放什么”下的依赖方向 |
| `calc_dependency`、`calc_purity` | calc 用了不纯的导入或调用 |
| `library_layout`、`library_exports`、`library_declaration` | 工具包的结构、`exports` 和 `__all__` 对不上 |
| `unused_exception` | `rules.py` 里登记的例外已经用不上，删掉它 |
| `writing_style` | Skill 文字里有公文腔 |

检查没过就改代码，不改阈值、不改 `tests/architecture` 和 `tests/quality` 的断言、不跳过测试。

## 接口文档

项目只生成一份文档 `doc/api/openapi.json`，给前端和 `dev compare-api` 用。改了接口运行 `uv run dev docs` 更新，完整检查会核对它是不是最新的。

## 检查失败时

1. 读输出里附带的中文运行报告，找到失败的步骤和源码行。完整报告在 `server/var/development/failures/`，不提交。
2. 判断是哪一类：代码写错、测试安排错、缺真实数据来源、功能还没做。
3. 修问题本身，修完重跑同一条命令。

## 写测试

- 预期结果来自和用户确认过的业务样例。旧系统的输出只用来比较，不当标准答案。
- 和时间有关的样例，在执行时传入时间或用可控时钟，不放宽业务时限。
- 权限测试用真实的应用权限。
- 目录分组、测试准备函数、单步测试、数据库和手动测试见[测试说明](references/tests.md)。

## 有界状态检查

修改任务领取、接管或提交原子性时，单独执行 `uv run dev verify-model`。它检查小规模状态空间、检测刻意损坏的模型，再跑真实提交回滚测试；不进入日常 `dev check`。范围与代码对应关系见[任务状态模型](references/job-model.md)。
