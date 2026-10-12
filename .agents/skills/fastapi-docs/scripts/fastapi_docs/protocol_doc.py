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
        "| 接口 | 方法与路径 | 效果 | 输入 | 输出 | 待确认 | 确定拒绝 | 校验范围 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
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
            "明确字段，拒绝扩展" if endpoint.shape()["validation"]["complete"] else "部分验证",
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]


# 外部发送协议与重复保证来自同一声明，运行受理和完成不从文档推定。
def provider_section(module: Module) -> list[str]:
    if not module.providers:
        return []
    lines = [
        "## 外部效果",
        "",
        "| 操作 | 传输 | 输入 | 回执 | 可安全重复 | 预算秒 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for spec in module.providers:
        values = [
            spec.name,
            spec.transport,
            spec.input.__name__,
            spec.output.__name__,
            "是" if spec.repeat_safe else "否，未知结果先查证",
            spec.timeout,
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]
