# $title（$name）

## 用途

（用两三句话写清楚：这个模块为谁解决什么问题，明确不做什么。）

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| $name.create_record | 新建一条记录 | $name.write |
| $name.get_record | 按编号读取记录 | $name.read |

## 依赖

目前不调用其他模块。调用其他模块时，在步骤的 uses 中声明，并在这里写明原因。

## 内部组织

- `module.json`：生成器提供的标准结构说明，不能自行扩展允许的文件范围。
- `data.py`：公开数据、流程数据、业务错误。
- `flow.py`：每个操作的步骤顺序。
- `steps/`：`check_record.py` 整理输入；`store_records.py` 读写数据库。
- `calc/`：可复用的标题计算，无数据库测试。
- `store/`：`contract.py` 声明需要的读写，`sql.py` 是数据库实现，`tables.py` 定义表。

## 测试

- `tests/modules/$name/`：单独测试步骤的计算规则。
- `tests/integration/$name/`：从 HTTP 接口测试完整流程。
