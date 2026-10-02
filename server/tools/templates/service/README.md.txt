# $title（$name）

## 用途

（用两三句话写清楚：这个模块为谁解决什么问题，明确不做什么。业务细节写在 doc/$name/。）

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| $name.create_record | 新建一条记录 | $name.write |
| $name.get_record | 按编号读取记录 | $name.read |

## 依赖

目前不调用其他模块。调用其他模块时，在步骤的 uses 中声明，并在这里写明原因。

## 内部组织

- `data.py`：公开数据、流程数据、业务错误。
- `flow.py`：每个操作的步骤顺序。
- `steps/`：`check_record.py` 整理输入；`store_records.py` 读写数据库。
- `store/`：`contract.py` 声明需要的读写，`sql.py` 是数据库实现，`tables.py` 定义表。

## 业务文档

需求、规则和变化记录见 [doc/$name](../../../doc/$name/)；流程图和字段来源见其中自动生成的 flows.md。

## 测试

- `tests/modules/$name/`：单独测试步骤的计算规则。
- `tests/integration/$name/`：从 HTTP 接口测试完整流程。
