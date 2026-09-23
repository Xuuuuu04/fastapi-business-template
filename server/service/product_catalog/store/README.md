# 商品目录的数据访问

- `contract.py`：步骤需要的读写操作 `ProductStore`。步骤只依赖这个约定。
- `sql.py`：数据库实现。唯一约束冲突在保存点中转成 `CodeUsed`。
- `tables.py`：表 `product_catalog_items`。

商品数据改从其他系统读取时，新写一个实现 `ProductStore` 的类，在 module.py 中替换 `store=`，步骤不用改。
