# 从独立样例到真实实现

以下命令在 `server` 目录执行。先写输入、初始状态和预期样例，再写包契约与步骤规格；不要从已写好的实现反推预期。正式模板保持 `MODULES=[]`，业务只生成到新项目中。

1. `uv run dev skeleton --spec ../skeleton.json --preview` 查看计划写入的文件；去掉 `--preview` 才生成。规格必须明确字段类型、权限、包类别、调用输入和返回映射，参考 `SkeletonBundle` 的 JSON Schema。短生成器不代写数据库初始化或外部效果断言，这些样例需要单独编写真实测试。
2. `uv run dev start --package 包名 --cases R-01-C01,R-01-C02` 创建任务卡，保存规则、契约、基线和允许修改的范围。记录返回的任务编号。
3. 替换步骤中的模拟实现。模拟提供者仅放测试中，通过 `simulate` 注入；生产组装与交付检查拒绝仍然声明 `simulated=True` 的步骤。真实步骤不能复制样例中的预期值。
4. `uv run dev finish --task 任务编号 --postgres 控制数据库连接` 实际检查本包和调用方，并保存本次证据及审查单。工作流需要 SQLite 与 PostgreSQL 同轮通过；失败、跳过、旧源码或模拟执行都不能完成任务。连接信息只在本机使用，不写进任务卡、文档或提交。
5. `uv run dev review-pack --task 任务编号` 导出规则、独立样例和准确基线差异，供复核；材料不附实现者的检查结论。范围之外的改动仍在收工审查单中明确列出。

契约不合适时，用 `uv run dev ask-contract --package 包名 --reason 原因 --suggestion 建议` 保存请求，再统一修改公开契约。相关规则、契约或实际调用关系变化后，旧任务会显示需要更新。`uv run dev status --summary --json` 查看当前任务状态和检查来源；这些状态不证明业务已经验收，也不验证操作者身份。

任务卡、基线和检查证据留在本机 `.agents/records`、`server/var/development` 中。保留它们才能复查；丢失证据会明确显示未完成。骨架生成成功只表示文件结构建立，真实实现、测试通过和规则确认需要分别判断。
