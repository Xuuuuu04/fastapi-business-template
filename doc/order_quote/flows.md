# 订单报价：操作与流程

> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；业务含义写在 needs.md 和 rules.md。

模块 `order_quote`，版本 1。调用的其他模块：product_catalog（查询可报价的单价）。

## 公开操作

| 操作 | 名称 | 权限 | 接口 | 可能的业务错误 |
| --- | --- | --- | --- | --- |
| create_quote | 创建报价 | order_quote.write | POST /api/v1/quotes | nothing_to_quote（所有商品都不能报价：不存在、已停售或尚未定价） |
| get_quote | 读取报价 | order_quote.read | GET /api/v1/quotes/{quote_id} | quote_missing（报价不存在） |
| expire_quotes | 标记过期报价 | order_quote.manage | POST /api/v1/quotes/expire<br/>定时计划 | 无 |

## 创建报价（order_quote.create_quote）

输入 `QuoteRequest`，输出 `QuoteView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：客户名称、会员等级：none 非会员，silver 银卡，gold 金卡、报价明细"])
    s1["1. 合并明细（计算）<br/>规则 R-01"]:::compute
    start --> s1
    s2["2. 查询商品单价（调用）<br/>规则 R-02"]:::call
    s1 --> s2
    c_product_catalog_get_prices[["调用：查询可报价的单价（product_catalog.get_prices）"]]
    s2 -.-> c_product_catalog_get_prices
    s3["3. 计算金额（计算）<br/>规则 R-02"]:::compute
    s2 --> s3
    s4["4. 计算会员优惠（计算）<br/>规则 R-03"]:::compute
    s3 -->|"条件：客户是会员"| s4
    s5["5. 计算应付金额（计算）<br/>规则 R-04"]:::compute
    s4 --> s5
    s6["6. 生成报价说明（大模型）<br/>规则 R-05"]:::model
    s5 --> s6
    p_explain_quote>"提示词：报价说明 v1"]
    s6 -.-> p_explain_quote
    s7["7. 保存报价（保存）"]:::save
    s6 --> s7
    s8["8. 整理报价（计算）"]:::compute
    s7 --> s8
    finish(["结果：返回给调用方的报价"])
    s8 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| customer | 客户名称 | 操作输入 |  |  |  |
| member_level | 会员等级 | 操作输入 |  | R-03 |  |
| lines | 调用方提交的明细 | 操作输入 |  |  |  |
| merged_lines | 合并相同编码后的明细 | 步骤 | 合并明细 | R-01 | lines |
| unit_prices | 可报价商品的单价 | 步骤 | 查询商品单价 | R-02 | merged_lines、查询可报价的单价（product_catalog.get_prices） |
| excluded | 不能报价的商品编码 | 步骤 | 查询商品单价 | R-02 | merged_lines、查询可报价的单价（product_catalog.get_prices） |
| priced_lines | 计入报价的明细 | 步骤 | 计算金额 | R-02 | merged_lines、unit_prices、excluded |
| subtotal | 商品合计 | 步骤 | 计算金额 | R-02 | merged_lines、unit_prices、excluded |
| discount | 会员优惠 | 步骤 | 计算会员优惠 | R-03 | member_level、subtotal |
| total | 应付金额 | 步骤 | 计算应付金额 | R-04 | subtotal、discount |
| explanation | 报价说明 | 步骤 | 生成报价说明 | R-05 | customer、priced_lines、excluded、discount、total |
| saved_id | 保存后的报价编号 | 步骤 | 保存报价 |  | customer、member_level、priced_lines、excluded、subtotal、discount、total、explanation |
| created_at | 保存时间（UTC） | 步骤 | 保存报价 |  | customer、member_level、priced_lines、excluded、subtotal、discount、total、explanation |
| quote | 返回给调用方的报价 | 步骤 | 整理报价 |  | saved_id、customer、member_level、priced_lines、excluded、subtotal、discount、total、explanation、created_at |

## 读取报价（order_quote.get_quote）

输入 `QuoteId`，输出 `QuoteView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：报价编号"])
    s1["1. 读取报价（读取）"]:::read
    start --> s1
    finish(["结果：读取到的报价"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| quote_id | 报价编号 | 操作输入 |  |  |  |
| quote | 读取到的报价 | 步骤 | 读取报价 |  | quote_id |

## 标记过期报价（order_quote.expire_quotes）

输入 `ExpireRequest`，输出 `ExpireResult`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：创建超过多少天的有效报价标为过期"])
    s1["1. 标记过期报价（保存）<br/>规则 R-06"]:::save
    start --> s1
    finish(["结果：处理结果"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| days | 过期天数 | 操作输入 |  | R-06 |  |
| result | 处理结果 | 步骤 | 标记过期报价 | R-06 | days |

## 数据模型

### QuoteRequest

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| customer | str | 是 | 客户名称 |  |  |  |
| member_level | Literal['none', 'silver', 'gold'] | 是 | 会员等级：none 非会员，silver 银卡，gold 金卡 |  |  | R-03 |
| lines | list[QuoteLineInput] | 是 | 报价明细 |  |  |  |

### QuoteLineInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 商品编码 |  |  |  |
| quantity | int | 是 | 数量 |  |  |  |

### QuoteView

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 报价编号 |  |  |  |
| customer | str | 是 | 客户名称 |  |  |  |
| member_level | Literal['none', 'silver', 'gold'] | 是 | 会员等级 |  |  | R-03 |
| lines | list[QuoteLine] | 是 | 计入报价的明细 |  |  | R-02 |
| excluded | list[str] | 是 | 没有计入报价的商品编码：不存在、停售或未定价 |  |  | R-02 |
| subtotal | Decimal | 是 | 商品合计 | 元 |  | R-02 |
| discount | Decimal | 是 | 会员优惠 | 元 |  | R-03 |
| total | Decimal | 是 | 应付金额 | 元 |  | R-04 |
| explanation | str | 是 | 给客户看的报价说明，由大模型生成 |  |  | R-05 |
| status | Literal['active', 'expired'] | 是 | 报价状态：active 有效，expired 已过期 |  |  | R-06 |
| created_at | datetime | 是 | 创建时间（UTC） |  |  |  |

### QuoteLine

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 商品编码 |  |  |  |
| quantity | int | 是 | 数量；同一编码的多行已合并 |  |  | R-01 |
| unit_price | Decimal | 是 | 单价 | 元 |  | R-02 |
| amount | Decimal | 是 | 金额 = 单价 × 数量 | 元 |  | R-02 |

### QuoteId

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| quote_id | int | 是 | 报价编号 |  |  |  |

### ExpireRequest

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| days | int | 否 | 创建超过多少天的有效报价标为过期 |  |  | R-06 |

### ExpireResult

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| expired | int | 是 | 本次标为过期的报价数量 |  |  |  |

## 数据表

### order_quote_quotes

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| id | INTEGER |  | 是 |  |
| customer | VARCHAR(80) |  |  |  |
| member_level | VARCHAR(10) |  |  |  |
| subtotal | NUMERIC(14, 2) |  |  |  |
| discount | NUMERIC(14, 2) |  |  |  |
| total | NUMERIC(14, 2) |  |  |  |
| excluded | TEXT |  |  |  |
| explanation | TEXT |  |  |  |
| status | VARCHAR(10) |  |  |  |
| created_at | DATETIME |  |  |  |
| owner_id | VARCHAR(64) |  |  | 是 |

### order_quote_lines

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| id | INTEGER |  | 是 |  |
| quote_id | INTEGER |  |  |  |
| code | VARCHAR(40) |  |  |  |
| quantity | INTEGER |  |  |  |
| unit_price | NUMERIC(14, 2) |  |  |  |
| amount | NUMERIC(14, 2) |  |  |  |
