---
name: fastapi-check
description: 改完代码要验证、准备提交、或检查和测试报错时读，按这里选检查范围、看失败报告、写测试。部署和线上排查看 fastapi-operations。
---

# 检查和测试

`uv run dev check` 只做两件事：静态检查（风格、格式、类型、接口文档、代码规则）和跑测试。每次都真跑，不复制项目，也不沿用上次结果。命令在 `server/` 执行。

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

## 代码规则

检查报出的规则名和意思：

| 规则 | 意思 |
| --- | --- |
| `comment`、`docstring` | 代码里不写注释和文档字符串 |
| `catch` | 业务代码不写 try/except 和 suppress，写法见 fastapi-module“出错怎么办” |
| `file_lines`、`function_lines`、`nesting` | 文件超过 300 行、函数超过 50 行、嵌套超过 4 层，按用途拆开 |
| `blocking_call` | 异步代码里调用了同步等待 |
| `module_name`、`name_format`、`name_vague`、`step_name`、`condition_name` | 名字格式不对或太含糊（如 utils、helper） |
| `not_listed`、`missing_module`、`not_exposed`、`unused` | 模块登记和实际的包、入口、调用对不上 |
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
- 目录分组、夹具、单步测试、数据库和手动测试见[测试说明](references/tests.md)。
