# 商品目录：操作与流程

> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；业务含义写在 needs.md 和 rules.md。

模块 `product_catalog`，版本 1。调用的其他模块：无。

## 公开操作

| 操作 | 名称 | 权限 | 调用方式 | 可能的业务错误 |
| --- | --- | --- | --- | --- |
| list_products | 查询商品 | product_catalog.read | 接口或任务 | 无 |
| get_product | 读取商品 | product_catalog.read | 接口或任务 | product_missing（商品不存在） |
| create_product | 新建商品 | product_catalog.write | 接口或任务 | product_code_used（商品编码已被其他商品使用） |
| update_product | 修改商品 | product_catalog.write | 接口或任务 | product_missing（商品不存在）、product_code_used（商品编码已被其他商品使用） |
| delete_product | 删除商品 | product_catalog.write | 接口或任务 | product_missing（商品不存在） |
| get_prices | 查询可报价的单价 | product_catalog.read | 只供其他模块调用 | 无 |

## 查询商品（product_catalog.list_products）

输入 `ProductQuery`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| offset | int | 否 | 从第几条开始，从 0 计数 |  |  |  |
| limit | int | 否 | 本页最多返回多少条 |  |  |  |
| on_sale | bool \| None | 否 | 只看在售或只看停售 |  | 不按在售状态筛选 |  |

输出 `Page[ProductView]`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[ProductView] | 是 | 本页记录 |  |  |  |
| total | int | 是 | 符合条件的记录总数 |  |  |  |
| offset | int | 是 | 本页从第几条开始，从 0 计数 |  |  |  |
| limit | int | 是 | 本页最多返回多少条 |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：从第几条开始，从 0 计数、本页最多返回多少条、只看在售或只看停售"])
    s1["1. 读取商品列表（读取）"]:::read
    start --> s1
    finish(["结果：查询到的一页商品"])
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
| offset | 从第几条开始 | 操作输入 |  |  |  |
| limit | 本页最多返回多少条 | 操作输入 |  |  |  |
| on_sale | 在售状态筛选 | 操作输入 |  |  |  |
| page | 查询到的一页商品 | 步骤 | 读取商品列表 |  | offset、limit、on_sale |

## 读取商品（product_catalog.get_product）

输入 `ProductId`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| product_id | int | 是 | 商品编号 |  |  |  |

输出 `ProductView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 商品编号 |  |  |  |
| code | str | 是 | 商品编码 |  |  | R-01 |
| name | str | 是 | 商品名称 |  |  |  |
| price | Decimal \| None | 是 | 单价 | 元 | 尚未定价 | R-02 |
| on_sale | bool | 是 | 是否在售 |  |  | R-02 |
| updated_at | datetime | 是 | 最后修改时间（UTC） |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：商品编号"])
    s1["1. 读取商品（读取）"]:::read
    start --> s1
    finish(["结果：读取到的商品"])
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
| product_id | 商品编号 | 操作输入 |  |  |  |
| product | 读取到的商品 | 步骤 | 读取商品 |  | product_id |

## 新建商品（product_catalog.create_product）

输入 `ProductInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 商品编码，保存前去掉首尾空白并转成大写 |  |  | R-01 |
| name | str | 是 | 商品名称 |  |  |  |
| price | Decimal \| None | 否 | 单价 | 元 | 尚未定价，不能用于报价 | R-02 |
| on_sale | bool | 否 | 是否在售；停售的商品不能用于报价 |  |  | R-02 |

输出 `ProductView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 商品编号 |  |  |  |
| code | str | 是 | 商品编码 |  |  | R-01 |
| name | str | 是 | 商品名称 |  |  |  |
| price | Decimal \| None | 是 | 单价 | 元 | 尚未定价 | R-02 |
| on_sale | bool | 是 | 是否在售 |  |  | R-02 |
| updated_at | datetime | 是 | 最后修改时间（UTC） |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：商品编码，保存前去掉首尾空白并转成大写、商品名称、单价、是否在售；停售的商品不能用于报价"])
    s1["1. 整理商品编码（计算）<br/>规则 R-01"]:::compute
    start --> s1
    s2["2. 保存新商品（保存）"]:::save
    s1 --> s2
    finish(["结果：保存后的商品"])
    s2 --> finish
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
| code | 调用方填写的商品编码 | 操作输入 |  |  |  |
| name | 商品名称 | 操作输入 |  |  |  |
| price | 单价 | 操作输入 |  |  |  |
| on_sale | 是否在售 | 操作输入 |  |  |  |
| clean_code | 整理后的商品编码 | 步骤 | 整理商品编码 | R-01 | code |
| product | 保存后的商品 | 步骤 | 保存新商品 |  | clean_code、name、price、on_sale |

## 修改商品（product_catalog.update_product）

输入 `ProductChange`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 商品编码，保存前去掉首尾空白并转成大写 |  |  | R-01 |
| name | str | 是 | 商品名称 |  |  |  |
| price | Decimal \| None | 否 | 单价 | 元 | 尚未定价，不能用于报价 | R-02 |
| on_sale | bool | 否 | 是否在售；停售的商品不能用于报价 |  |  | R-02 |
| product_id | int | 是 | 要修改的商品编号 |  |  |  |

输出 `ProductView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 商品编号 |  |  |  |
| code | str | 是 | 商品编码 |  |  | R-01 |
| name | str | 是 | 商品名称 |  |  |  |
| price | Decimal \| None | 是 | 单价 | 元 | 尚未定价 | R-02 |
| on_sale | bool | 是 | 是否在售 |  |  | R-02 |
| updated_at | datetime | 是 | 最后修改时间（UTC） |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：商品编码，保存前去掉首尾空白并转成大写、商品名称、单价、是否在售；停售的商品不能用于报价、要修改的商品编号"])
    s1["1. 整理商品编码（计算）<br/>规则 R-01"]:::compute
    start --> s1
    s2["2. 保存商品修改（保存）"]:::save
    s1 --> s2
    finish(["结果：保存后的商品"])
    s2 --> finish
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
| code | 调用方填写的商品编码 | 操作输入 |  |  |  |
| name | 商品名称 | 操作输入 |  |  |  |
| price | 单价 | 操作输入 |  |  |  |
| on_sale | 是否在售 | 操作输入 |  |  |  |
| clean_code | 整理后的商品编码 | 步骤 | 整理商品编码 | R-01 | code |
| product | 保存后的商品 | 步骤 | 保存商品修改 |  | product_id、clean_code、name、price、on_sale |
| product_id | 要修改的商品编号 | 操作输入 |  |  |  |

## 删除商品（product_catalog.delete_product）

输入 `ProductId`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| product_id | int | 是 | 商品编号 |  |  |  |

输出 `Nothing`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

计算流程：

```mermaid
flowchart TD
    start(["输入：商品编号"])
    s1["1. 删除商品（保存）"]:::save
    start --> s1
    finish(["结果：删除完成的标记"])
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
| product_id | 要删除的商品编号 | 操作输入 |  |  |  |
| done | 删除完成的标记 | 步骤 | 删除商品 |  | product_id |

## 查询可报价的单价（product_catalog.get_prices）

输入 `PriceQuery`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| codes | list[str] | 是 | 要查询单价的商品编码 |  |  |  |

输出 `PriceList`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| prices | dict[str, Decimal] | 是 | 可以报价的商品单价，按商品编码对应 | 元 |  | R-02 |
| missing | list[str] | 是 | 不能报价的商品编码：不存在、已停售或尚未定价 |  |  | R-02 |

计算流程：

```mermaid
flowchart TD
    start(["输入：要查询单价的商品编码"])
    s1["1. 读取可报价单价（读取）<br/>规则 R-02"]:::read
    start --> s1
    finish(["结果：查询结果"])
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
| codes | 要查询单价的商品编码 | 操作输入 |  |  |  |
| prices | 查询结果 | 步骤 | 读取可报价单价 | R-02 | codes |
