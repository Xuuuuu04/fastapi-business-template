# 订单报价（order_quote）

## 职责

根据客户和商品明细计算报价：合并明细、向商品目录查询单价、计算金额和会员优惠、请大模型写一段给客户看的说明、保存报价。每天凌晨把过期的报价标为过期。不负责下单和收款。

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| order_quote.create_quote | 计算并保存一份报价 | order_quote.write |
| order_quote.get_quote | 按编号读取报价 | order_quote.read |
| order_quote.expire_quotes | 把创建超过指定天数的有效报价标为过期；作为后台任务运行，并有每日定时计划 | order_quote.manage |

## 依赖

调用商品目录的 `product_catalog.get_prices` 查询可以报价的单价（步骤“查询商品单价”）。

## 内部组织

- `data.py`：报价的公开数据、流程数据 `QuoteWork`；错误 `QuoteMissing`、`NothingToQuote`。
- `flow.py`：创建报价共 8 步：合并明细、查询商品单价、计算金额、计算会员优惠（只对会员）、计算应付金额、生成报价说明、保存报价、整理报价。先计算和调用大模型，最后才保存，避免写入事务等待模型。
- `steps/quote_rules.py`：R-01 至 R-04 的计算，全部是纯计算；`ask_others.py`：调用商品目录和大模型；`store_quotes.py`：读写数据库。
- `store/`：`QuoteStore` 约定和数据库实现，表 `order_quote_quotes`、`order_quote_lines`。报价表用 `owner_column` 按负责人隔离（R-07），`store/sql.py` 的 `mine()` 给出限定条件。
- `prompts/explain_quote.md`：报价说明的提示词，版本 1。

## 业务文档

[doc/order_quote](../../../doc/order_quote/)：需求、规则 R-01 至 R-07、变化记录，以及自动生成的流程图和字段来源。

## 测试

- `tests/modules/order_quote/`：规则 R-01 至 R-05 的确认样例。
- `tests/integration/order_quote/`：从 HTTP 接口创建和读取报价、查看诊断报告、执行后台任务。
