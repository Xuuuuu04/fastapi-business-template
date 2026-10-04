# 项目设计与结构进度

> 由 tools.export_docs 生成。计划来自 project-plan.json；登记数量来自代码，不能表示测试通过。

实际检查轮次与操作成功执行情况：`uv run python -m tools.project`。
模块内部步骤、条件、源码与上轮测试：`uv run python -m tools.project --module 模块名`。

```mermaid
flowchart TD
    root["FastAPI 通用后端模板"]
    line0["通用能力"]
    root --> line0
    m_user_access["用户权限：登记 18/18"]
    line0 --> m_user_access
    m_file_library["文件管理：登记 5/5"]
    line0 --> m_file_library
```

| 业务线 | 开发包 | 已登记/计划操作 | 尚未登记 |
| --- | --- | --- | --- |
| 通用能力 | user_access | 18/18 | 无 |
| 通用能力 | file_library | 5/5 | 无 |
