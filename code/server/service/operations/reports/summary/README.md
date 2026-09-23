# 示例：汇总报表

## 1. 业务用途

按给定范围产生汇总结果，供运营查看或导出。这里只演示分包，不预设具体指标或计算规则。

## 2. 建议的文件

| 文件 | 有实际代码时承担的职责 |
| --- | --- |
| service.py | 汇总操作入口，组织读取、计算和结果保存 |
| types.py | 本功能输入与结果的业务类型 |
| needs.py | 本业务需要外部提供的读取与保存操作 |
| store/read.py | 本地数据库查询，需要时建立 |
| rules.py | 不访问网络和数据库的计算规则 |
| export.py | 导出业务结果，需要下载时建立 |
| store/table.py | 本功能独有的表，需要持久化时建立 |

这些是建议位置，尚未创建占位 Python 文件。

## 3. 对应位置

HTTP 路由未来放 app/api/routes/operations/reports；单元测试对应 tests/unit/service/operations/reports；需要数据库的完整流程放 tests/integration/service/operations/reports。

两个报表共用的计算或导出组件提取到相邻 shared。共享事实数据引用 service/data 中的对象定义，避免复制另一功能的私有表和规则。

## 4. 实现前需要明确

由实际项目决定汇总维度、日期范围、缺失值处理和用户可查看的对象范围。未定义统计口径前，不填入看似真实的示例计算。
