# 模块关系

> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；业务含义写在 各模块目录。

| 模块 | 名称 | 版本 | 业务文档 |
| --- | --- | --- | --- |
| product_catalog | 商品目录 | 1 | [product_catalog/](product_catalog/) |
| order_quote | 订单报价 | 1 | [order_quote/](order_quote/) |

```mermaid
flowchart LR
    m_product_catalog["商品目录（product_catalog，版本 1）"]
    m_order_quote["订单报价（order_quote，版本 1）"]
    m_order_quote -->|"查询可报价的单价"| m_product_catalog
```
