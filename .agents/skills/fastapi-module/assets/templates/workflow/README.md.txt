# $title（$name）

## 用途

（用两三句话写清楚：这个流程包把哪些能力包串成什么业务链，明确不做什么。）

## 公开操作

用 `uv run dev new-operation $name 操作名 --title 中文名` 添加，生成器会把操作列在这里。

## 依赖

流程包只调用能力包的公开操作，在步骤的 uses 中声明；不调用其他流程包，不拥有数据表。

## 内部组织

- `module.json`：生成器提供的标准结构说明，kind 是 workflow。
- `data.py`：公开数据、流程数据、业务错误。
- `flow.py`：每个操作的步骤顺序；操作多了可以拆成 `flow_主题.py`。
- `steps/`：连接各能力包的步骤和纯计算。

## 测试

- `tests/modules/$name/`：单独测试步骤。
- `tests/integration/$name/`：从 HTTP 接口测试完整业务链。
