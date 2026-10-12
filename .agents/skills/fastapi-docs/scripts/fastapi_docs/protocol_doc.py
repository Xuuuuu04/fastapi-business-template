"""
外部协议声明的文档表格，与内部业务流程章节分别维护。
"""

from fastapi_docs.progress_doc import cell

from shared.modules.module import Module


# 上游接口协议与模型从同一份声明生成，产品文档无需再手写解析格式。
def endpoint_section(module: Module) -> list[str]:
    if not module.endpoints:
        return []
    lines = [
        "## 上游接口",
        "",
        "| 接口 | 方法与路径 | 效果 | 输入 | 输出 | 待确认 | 确定拒绝 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for endpoint in module.endpoints:
        values = [
            endpoint.name,
            f"{endpoint.method} {endpoint.path}",
            endpoint.effect,
            endpoint.input.__name__,
            endpoint.output.__name__,
            str(endpoint.unknown_on),
            str(endpoint.accepted_statuses),
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]
