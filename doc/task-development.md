# 从独立样例到真实实现

以下命令在 `server` 目录执行。先写输入、初始状态和预期样例，再写包契约与步骤规格；不要从已写好的实现反推预期。正式模板保持 `MODULES=[]`，业务只生成到新项目中。

1. 先用 `uv run dev skeleton --init --spec ../skeleton.json` 生成每个操作的样例和规则模板，已有文件不覆盖。编号、字段占位和 tests 引用自动填好；独立填写业务值和规则后，用 `uv run dev skeleton --spec ../skeleton.json --preview` 查看文件，再去掉 `--preview` 生成骨架。短生成器不代写数据库初始化或外部效果断言，这些样例需要单独编写真实测试。
2. `uv run dev start --package 包名 --cases R-01-C01,R-01-C02` 创建任务卡，保存规则、契约、基线和允许修改的范围。记录返回的任务编号。
3. 替换步骤中的模拟实现。模拟提供者仅放测试中，通过 `simulate` 注入；生产组装与交付检查拒绝仍然声明 `simulated=True` 的步骤。真实步骤不能复制样例中的预期值。
4. `uv run dev finish --task 任务编号` 实际检查本包和调用方，并保存本次证据及审查单。本包必须已替换所有模拟步骤，相关链测试必须通过；兄弟包仍模拟只提示，不影响按包收工。默认本轮跑 SQLite，提供 `--postgres 控制数据库连接` 时两库同轮通过。失败、跳过和旧源码不能完成任务；只有 `check --delivery` 要求全部包真实实现。连接信息只在本机使用，不写进任务卡、文档或提交。
5. `uv run dev review-pack --task 任务编号` 导出规则、独立样例和准确基线差异，供复核；材料不附实现者的检查结论。范围之外的改动仍在收工审查单中明确列出。

## 可直接使用的最小规格

在项目根目录保存 `skeleton.json`（此例运费为件数乘 100，独立样例先写输入 2、预期 200）：

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

```bash
uv run dev skeleton --init --spec ../skeleton.json
# 编辑 doc/order_shipping/cases/order_shipping.R-01-C01.json：input.quantity=2、expected.amount=200
# 编辑 doc/order_shipping/rules.md：填写 R-01 的业务规则；占位值不是业务验收
uv run dev skeleton --spec ../skeleton.json
uv run dev start --package order_shipping --cases R-01-C01
# 替换 server/service/order_shipping/steps/build_fee.py 的实现，设置 simulated=False
uv run dev docs
uv run dev finish --task 返回的编号
uv run dev check --database sqlite --delivery
```

字段支持 str、int、float、bool、list[str]、list[int]、dict[str, str]、dict[str, int]。权限只用 public、signed_in 或 order_shipping.权限名。流程包声明 `kind=workflow`，用 calls 的 operation、input 和 case 连接操作，returns 指定最终字段来源；完整三包连接见 `server/tests/framework/skeleton_sample.py`。权限、字段、调用和样例在任何业务文件写入之前检查。

契约不合适时，用 `uv run dev ask-contract --package 包名 --reason 原因 --suggestion 建议` 保存请求，再统一修改公开契约。相关规则、契约或实际调用关系变化后，旧任务会显示需要更新。`uv run dev status --summary --json` 查看当前任务状态和检查来源；这些状态不证明业务已经验收，也不验证操作者身份。

任务卡、基线和检查证据留在本机 `.agents/records`、`server/var/development` 中。保留它们才能复查；丢失证据会明确显示未完成。骨架生成成功只表示文件结构建立，真实实现、测试通过和规则确认需要分别判断。
