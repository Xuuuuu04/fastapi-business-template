# quality：质量检查

每个文件是一类检查，返回问题清单（文件、行号、规则、说明、整理建议），不修改任何文件。`tests/quality` 在默认测试中运行它们，并用故意写错的样例证明每条检查确实会失败。

| 文件 | 检查 |
| --- | --- |
| [files.py](files.py) | 文件头多行中文说明、函数前单行中文说明、待办标记、文件 300 行、函数 50 行、嵌套 4 层、函数内连续注释 |
| [naming.py](naming.py) | 小写下划线、含义模糊的名字、模块名至少两个词、步骤名“动词_对象”、条件名 is/has/can 开头 |
| [imports.py](imports.py) | 依赖方向：业务只用 shared.public 和其他模块的 public.py、数据库库只在 store/、禁止动态和相对导入 |
| [blocking.py](blocking.py) | async 函数中的阻塞调用 |
| [readmes.py](readmes.py) | 目录 README、长度、模块 README 的固定小节和公开操作 |
| [docs.py](docs.py) | 业务文档齐全、长度、规则编号在 rules.md 中存在、生成文档未过期 |
| [registry.py](registry.py) | 模块都已登记、每个操作都有测试、对外操作接到了接口或任务、内部操作被调用 |
| [rules.py](rules.py) | 阈值、允许的动词、例外登记 |

超过上限时按建议整理：保留全部业务条件和确认样例，不要为了过检查把代码挤成一行或删掉文档内容。确实需要例外时登记在 rules.py 的 `ALLOWED`，写明原因；修改阈值和例外属于框架改动。
