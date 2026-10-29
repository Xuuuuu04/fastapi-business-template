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

从最小范围开始，改了公共代码再跑全部。`--quick` 不跑类型检查和接口文档核对。

## 真跑一次看结果

检查过了还要亲眼看一次真实运行。用本地 `.env` 的数据库跑一次登记的操作，打印结果和运行报告（每一步读写了什么、调了谁、停在哪）：

```bash
uv run dev run customer_contact.create_contact --input '{"name": "张三"}'
uv run dev run customer_contact.create_contact --input-file 样例.json --org north
```

以本地开发者身份运行，拥有全部权限；`--org` 指定组织。成功退出码 0，失败 1，失败时报告写明停在哪一步、为什么。本地库要先 `uv run alembic upgrade head`。多阶段流程按阶段分别跑。

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
