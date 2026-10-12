"""
把应用的 OpenAPI 描述整理成中文接口清单（Markdown），不启动服务、不连接数据库。
"""

import json
from typing import Any

from fastapi import FastAPI

from app.setup.application import application
from app.setup.web import create_app

METHODS = ("get", "post", "put", "patch", "delete")
LIMITS = {
    "minLength": "最短",
    "maxLength": "最长",
    "minimum": "最小",
    "maximum": "最大",
    "exclusiveMinimum": "大于",
    "enum": "可选值",
}
# FastAPI 自动生成的状态码说明是英文，这里换成中文；业务自己写的说明保持原样。
STATUS_TEXT = {
    "Successful Response": "请求成功",
    "Validation Error": "输入不符合要求",
    "No Content": "成功，没有返回内容",
    "Not Found": "没有找到这个路径",
}
# 框架自动生成的模型名显示成中文，括号里保留原名便于对照。
MODEL_TEXT = {
    "HTTPValidationError": "输入错误明细（HTTPValidationError）",
    "ValidationError": "输入错误（ValidationError）",
}


# 用于生成文档的应用：测试配置、开放接口文档，不连接外部服务。
def docs_app(name: str | None = None) -> FastAPI:
    settings = application().settings("offline", docs=True)
    if name is not None:
        settings.name = name
    return create_app(settings)


# 生成 OpenAPI 描述和中文接口清单。
def api_markdown(app: FastAPI) -> tuple[dict[str, Any], str]:
    schema = app.openapi()
    lines = [
        f"# {schema['info']['title']} 接口清单",
        "",
        "这份清单根据服务的实际路由自动生成。调用接口时，服务密钥放在请求头 X-API-Key 里。",
        "",
    ]
    for path, entries in schema["paths"].items():
        for method, item in entries.items():
            if method in METHODS:
                lines += operation_lines(method, path, item)
    lines += ["## 数据模型", ""]
    for name, model in schema.get("components", {}).get("schemas", {}).items():
        lines += model_lines(name, model)
    return schema, "\n".join(lines)


# 生成一个接口的说明。
def operation_lines(method: str, path: str, item: dict[str, Any]) -> list[str]:
    lines = [f"## {method.upper()} {path}", "", f"用途：{item.get('summary', '')}"]
    lines += [
        f"分组：{'、'.join(item.get('tags', []))}",
        f"操作编号：{item.get('operationId', '')}",
        "",
    ]
    params = item.get("parameters", [])
    if params:
        lines += [
            "| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for param in params:
            model = param.get("schema", {})
            values = [param["name"], param["in"], "是" if param.get("required") else "否"]
            values += [type_name(model), limits(model), param.get("description", "")]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
        lines.append("")
    for kind, detail in item.get("requestBody", {}).get("content", {}).items():
        lines += [f"请求正文：{kind}，模型 {type_name(detail['schema'])}。", ""]
    lines += ["| 状态码 | 含义 | 返回模型 |", "| --- | --- | --- |"]
    for status, reply in item["responses"].items():
        models = [type_name(part.get("schema", {})) for part in reply.get("content", {}).values()]
        description = STATUS_TEXT.get(reply.get("description", ""), reply.get("description", ""))
        lines.append(f"| {status} | {cell(description)} | {'、'.join(models) or '无返回内容'} |")
    return [*lines, ""]


# 生成一个数据模型的字段表。
def model_lines(name: str, model: dict[str, Any]) -> list[str]:
    lines = [
        f"### {name}",
        "",
        "| 字段 | 类型 | 必填 | 说明 | 限制 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field, detail in model.get("properties", {}).items():
        values = [field, type_name(detail), "是" if field in model.get("required", []) else "否"]
        values += [detail.get("description", ""), limits(detail)]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    if model.get("examples"):
        lines += [
            "",
            "示例：",
            "",
            "```json",
            json.dumps(model["examples"], ensure_ascii=False, indent=2),
            "```",
        ]
    return [*lines, ""]


# 把模型引用和组合类型整理成简短的类型说明。
def type_name(model: dict[str, Any]) -> str:
    if "$ref" in model:
        name = str(model["$ref"]).rsplit("/", 1)[-1]
        return MODEL_TEXT.get(name, name)
    if "anyOf" in model:
        return " 或 ".join(type_name(item) for item in model["anyOf"])
    if model.get("type") == "array":
        return f"列表[{type_name(model.get('items', {}))}]"
    return str(model.get("format", model.get("type", "无固定格式")))


# 把字段限制整理成文字。
def limits(model: dict[str, Any]) -> str:
    return "；".join(f"{label}：{model[key]}" for key, label in LIMITS.items() if key in model)


# 整理表格单元格。
def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
