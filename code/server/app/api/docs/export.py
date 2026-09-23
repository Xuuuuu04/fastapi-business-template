"""
离线导出全局 OpenAPI 和中文接口清单。
直接使用应用路由，不启动服务器或连接数据库。
"""

import argparse
import json
from pathlib import Path

from app.setup.app import create_app
from shared.config.settings import Settings

METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


# 将字段内容整理为不会破坏 Markdown 表格的文本。
def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


# 将模型引用和组合类型整理为简短类型说明。
def type_name(model: dict) -> str:
    if "$ref" in model:
        return model["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in model:
        return " 或 ".join(type_name(item) for item in model["anyOf"])
    if model.get("type") == "array":
        return f"列表[{type_name(model.get('items', {}))}]"
    return model.get("format", model.get("type", "未指定"))


# 将字段限制转换为便于核对的文字。
def limits(model: dict) -> str:
    names = {
        "minLength": "最短",
        "maxLength": "最长",
        "minimum": "最小",
        "maximum": "最大",
        "exclusiveMinimum": "大于",
        "enum": "可选值",
    }
    return "；".join(f"{label}：{model[key]}" for key, label in names.items() if key in model)


# 将接口和完整模型转换为可检查的中文 Markdown。
def render(schema: dict) -> str:
    lines = [
        f"# {schema['info']['title']} API",
        "",
        f"版本：{schema['info']['version']}",
        "",
        "由运行路由自动生成。WriteKey 使用 X-API-Key；MonitorKey 使用 X-Monitor-Key。",
        "",
    ]
    for path, entries in schema["paths"].items():
        for method, item in entries.items():
            if method not in METHODS:
                continue
            lines.extend(
                [
                    f"## {method.upper()} {path}",
                    "",
                    f"用途：{item.get('summary', '')}",
                    f"分组：{', '.join(item.get('tags', []))}",
                    f"操作编号：{item.get('operationId', '')}",
                    f"权限：{item.get('security') or '公开'}",
                    "",
                ]
            )
            params = item.get("parameters", [])
            if params:
                lines.extend(
                    ["| 参数 | 位置 | 必填 | 类型 | 限制 |", "| --- | --- | --- | --- | --- |"]
                )
                for param in params:
                    model = param.get("schema", {})
                    fields = [
                        param["name"],
                        param["in"],
                        "是" if param.get("required") else "否",
                        type_name(model),
                        limits(model),
                    ]
                    lines.append("| " + " | ".join(cell(field) for field in fields) + " |")
                lines.append("")
            body = item.get("requestBody", {}).get("content", {})
            for kind, detail in body.items():
                lines.extend([f"请求正文：{kind}，模型 {type_name(detail['schema'])}。", ""])
            lines.extend(["| 状态码 | 含义 | 返回模型 |", "| --- | --- | --- |"])
            for status, reply in item["responses"].items():
                models = [
                    type_name(part.get("schema", {}))
                    for part in reply.get("content", {}).values()
                ]
                fields = [status, reply.get("description", ""), "、".join(models) or "空响应"]
                lines.append("| " + " | ".join(cell(field) for field in fields) + " |")
            lines.append("")
    lines.extend(["## 数据模型", "", "模型名称对应接口中的请求与返回类型。", ""])
    for name, model in schema.get("components", {}).get("schemas", {}).items():
        lines.extend(
            [
                f"### {name}",
                "",
                "| 字段 | 类型 | 必填 | 说明 | 限制 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for name, field in model.get("properties", {}).items():
            fields = [
                name,
                type_name(field),
                "是" if name in model.get("required", []) else "否",
                field.get("description", ""),
                limits(field),
            ]
            lines.append("| " + " | ".join(cell(value) for value in fields) + " |")
        lines.append("")
        if model.get("examples"):
            lines.extend(
                [
                    "示例：",
                    "",
                    "```json",
                    json.dumps(model["examples"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines)


# 从实际路由生成两份文档并写入指定目录。
def export(output: Path) -> dict:
    settings = Settings(_env_file=None)
    app = create_app(settings)
    schema = app.openapi()
    output.mkdir(parents=True, exist_ok=True)
    (output / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "index.md").write_text(render(schema), encoding="utf-8")
    return schema


# 解析文档输出目录并执行离线导出。
def main() -> None:
    parser = argparse.ArgumentParser(description="导出全局 API 文档")
    parser.add_argument("--output", type=Path, default=Path("out/api"))
    args = parser.parse_args()
    export(args.output)
    print(f"文档已导出到 {args.output}")


if __name__ == "__main__":
    main()
