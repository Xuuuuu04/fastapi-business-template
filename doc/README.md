# 业务文档

这里只记录业务：谁在用、要解决什么问题、每个字段是什么意思、怎么计算、遇到异常怎么办、哪些已经确认、什么时候变过。技术说明写在代码目录的 README 中，不放在这里。

## 模块

| 模块 | 名称 | 文档 |
| --- | --- | --- |
| product_catalog | 商品目录 | [需求](product_catalog/needs.md) · [规则](product_catalog/rules.md) · [变化](product_catalog/changes.md) · [流程](product_catalog/flows.md) |
| order_quote | 订单报价 | [需求](order_quote/needs.md) · [规则](order_quote/rules.md) · [变化](order_quote/changes.md) · [流程](order_quote/flows.md) |
| user_access | 用户权限 | [需求](user_access/needs.md) · [规则](user_access/rules.md) · [变化](user_access/changes.md) · [流程](user_access/flows.md) |
| file_library | 文件管理 | [需求](file_library/needs.md) · [规则](file_library/rules.md) · [变化](file_library/changes.md) · [流程](file_library/flows.md) |

模块之间的关系见 [modules.md](modules.md)（自动生成）。

## 每个模块的四份文档

| 文件 | 写什么 | 谁维护 |
| --- | --- | --- |
| needs.md | 谁使用、要解决什么问题、有哪些功能、明确不做什么 | 人确认后写入 |
| rules.md | 字段含义、每条规则的编号和计算方法、异常情况、确认样例、业务流程图 | 人确认后写入；代码中的 `rule="R-xx"` 必须能在这里找到 |
| changes.md | 已确认的业务变化：日期、确认人、改了什么、何时生效、对旧数据和旧接口的影响 | 每次业务变化时追加 |
| flows.md | 每个操作的输入输出、计算流程图、字段来源 | `tools.export_docs` 自动生成，不要手改 |

## 写法要求

- 用业务语言写，让没有看过代码的人也能判断对不对。
- 没有确认的内容写“待确认”，不要让 AI 自行补全。
- 每份文档不超过 200 行；变长时按业务主题拆分，保留全部业务条件和确认样例。
- 业务改了先改文档，再改代码和测试；测试的预期值来自这里的确认样例。

## 术语

| 词 | 含义 |
| --- | --- |
| 可报价 | 商品在售并且已经定价 |
| 会员等级 | 客户的会员级别：非会员、银卡、金卡 |
