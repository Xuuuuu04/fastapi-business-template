# 商品目录（product_catalog）

## 职责

维护商品的编码、名称、单价和在售状态，并向其他模块提供“可以报价的单价”。不负责库存、采购和价格审批。

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| product_catalog.list_products | 分页查询商品，可按在售状态筛选 | product_catalog.read |
| product_catalog.get_product | 按编号读取商品 | product_catalog.read |
| product_catalog.create_product | 新建商品，编码重复时报冲突 | product_catalog.write |
| product_catalog.update_product | 修改商品的全部字段 | product_catalog.write |
| product_catalog.delete_product | 删除商品 | product_catalog.write |
| product_catalog.import_products | 从 CSV 或 Excel 批量导入（R-03），有问题的行不导入并列出行号和原因 | product_catalog.write |
| product_catalog.export_products | 导出商品（R-04），列与导入相同 | product_catalog.read |
| product_catalog.get_prices | 查询在售且已定价的单价；只供其他模块调用，不对外开放 | product_catalog.read |

## 依赖

不调用其他模块。订单报价模块调用本模块的 get_prices。

## 内部组织

- `data.py`：商品的公开数据和流程数据；错误 `ProductMissing`、`CodeUsed`。
- `flow.py`：八个操作各对应一个流程，大多只有一两个步骤。
- `steps/check_product.py`：R-01 整理商品编码；`read_products.py`：读取；`save_products.py`：保存和删除；`import_products.py`：R-03 逐行检查与保存、R-04 读取导出内容。修改商品用 `update_tracked`，记入变更历史。
- `store/`：`ProductStore` 约定和数据库实现，表 `product_catalog_items`。

## 业务文档

[doc/product_catalog](../../../doc/product_catalog/)：需求、规则 R-01 至 R-04、变化记录，以及自动生成的流程图和字段来源。

## 测试

- `tests/modules/product_catalog/`：规则 R-01 至 R-03。
- `tests/integration/product_catalog/`：从 HTTP 接口测试增删改查、错误码、权限、变更历史，以及 CSV/Excel 导入导出。
