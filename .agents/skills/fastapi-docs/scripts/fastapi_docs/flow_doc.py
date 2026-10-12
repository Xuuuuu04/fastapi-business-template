"""
生成 doc/模块名/flows.md：公开操作与接口路径、每个操作的流程图和字段来源、数据模型、数据表。
同一个数据模型只展开一次，操作章节只写模型名，改动时差异集中、便于审查。
接口路径从实际路由中读取：看每个接口函数引用了哪些操作约定，不靠名字猜测。
图上的节点只放序号和业务标题；规则、代码位置、读写字段放在图下方的表格里，两边分工。
"""

import ast
import inspect
import re
import textwrap
from collections.abc import Iterable
from types import ModuleType
from typing import Any, get_args

from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel
from sqlalchemy import Table

from shared.data.fields import notes_of
from shared.graphs.lineage import field_sources
from shared.graphs.static import flow_graph
from shared.graphs.steps import location_text
from shared.modules.catalog import Binding, Catalog
from shared.modules.contract import Contract
from shared.modules.module import Module
from shared.records.models import STEP_KIND_TEXT
from shared.remote_calls.endpoint import Endpoint

HEADER = (
    "> 这份文件由命令 `uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py "
    "export_docs` 根据代码里的声明自动生成，请不要手工修改（改了也会在下次生成时被覆盖）。"
    "业务含义写在同目录的 needs.md（需求）和 rules.md（规则）里。"
)


# 读取每个操作约定对应的接口，例如 {"customer_contact.get_record": ["GET /api/v1/files/{org_id}"]}。
def route_map(app: FastAPI) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for route in iter_route_contexts(app.routes):
        if not isinstance(route.route, APIRoute):
            continue
        for name in contracts_used(route.endpoint):
            for method in sorted(route.methods or ()):
                found.setdefault(name, []).append(f"{method} {route.path}")
    return found


# 找出接口函数中以“模块.操作”形式引用的操作约定。
def contracts_used(endpoint: Any) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            item = endpoint.__globals__.get(node.id)
            if isinstance(item, Contract):
                names.add(item.name)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner = endpoint.__globals__.get(node.value.id)
            item = getattr(owner, node.attr, None) if isinstance(owner, ModuleType) else None
            if isinstance(item, Contract):
                names.add(item.name)
    return names


# 生成一个模块的 flows.md 全文。
def module_doc(catalog: Catalog, name: str, routes: dict[str, list[str]]) -> str:
    module = catalog.modules[name]
    links = catalog.links().get(name, {})
    depends = depend_text(links)
    lines = [f"# {module.title}：操作与流程", "", HEADER, ""]
    lines += [f"模块 `{name}`，版本 {module.version}。{depends}", ""]
    lines += reading_guide()
    lines += operation_table(module, routes)
    lines += error_table(module)
    for item in module.provides:
        lines += contract_section(catalog.bindings[item])
    lines += endpoint_section(module)
    lines += models_section([*module.provides, *module.endpoints])
    lines += tables_section(module.tables)
    return "\n".join(lines).rstrip() + "\n"


# 开头一段“怎么读”：图讲流程，表讲细节，各是什么。
def reading_guide() -> list[str]:
    return [
        "## 怎么读这份文档",
        "",
        "“公开操作”列出这个模块对外提供的服务。每个操作有一张流程图和两张明细表："
        "图上的节点只有序号和步骤名，用颜色区分步骤类型（蓝色是计算、绿色是读数据、"
        "橙色是写数据、紫色是调用其他模块、粉色是调用大模型）；"
        "“步骤明细”表补充每一步的规则编号和代码位置，“字段来源”表说明每个输出字段从哪一步来。"
        "业务错误统一在“业务错误一览”里解释一次，操作表里只写错误代码。",
        "",
    ]


# 依赖说明写成一句自然的话：每个模块给出操作总数和两三个例子，不再全部罗列。
def depend_text(links: dict[str, list[str]]) -> str:
    if not links:
        return "本模块不调用其他业务模块。"
    parts = []
    for target, titles in links.items():
        sample = "、".join(f"“{title}”" for title in titles[:3])
        total = f"共 {len(titles)} 个操作" if len(titles) > 3 else f"{len(titles)} 个操作"
        parts.append(f"{target}（{total}，如 {sample}）")
    return "本模块调用了这些模块：" + "、".join(parts) + "。具体调用关系画在各操作的流程图里。"


# 公开操作一览：名称、权限、接口路径、可能返回的错误代码（含义见错误一览表）。
def operation_table(module: Module, routes: dict[str, list[str]]) -> list[str]:
    lines = [
        "## 公开操作",
        "",
        "| 操作 | 名称 | 权限 | 接口 | 可能的业务错误 |",
        "| --- | --- | --- | --- | --- |",
    ]
    scheduled = {plan.contract for plan in module.schedules}
    queued = {plan.contract for plan in module.jobs}
    segmented = {plan.contract for plan in module.jobs if plan.segmented}
    for item in module.provides:
        ways = routes.get(item.name, []) if item.entry else ["只供其他模块调用"]
        ways += ["定时计划"] if item in scheduled else []
        ways += ["后台任务"] if item in queued and item not in scheduled else []
        ways += ["分段提交（按游标恢复）"] if item in segmented else []
        way = "<br/>".join(ways) or "没有接到接口或任务上"
        errors = "、".join(error.code for error in item.errors) or "无"
        values = [item.action, item.title, item.access, way, errors]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]


# 业务错误只解释一次：含义集中在这张表，其他位置只写错误代码。
def error_table(module: Module) -> list[str]:
    errors: dict[str, str] = {}
    for item in module.provides:
        for error in item.errors:
            errors.setdefault(error.code, error.message)
    if not errors:
        return []
    lines = [
        "## 业务错误一览",
        "",
        "| 错误代码 | 含义 |",
        "| --- | --- |",
    ]
    lines += [f"| {code} | {message} |" for code, message in errors.items()]
    return [*lines, ""]


# 一个操作的章节：输入输出、流程图、步骤明细、字段来源。
def contract_section(binding: Binding) -> list[str]:
    item = binding.contract
    lines = [f"## {item.title}（{item.name}）", ""]
    lines += [
        f"输入 `{model_name(item.input)}`，输出 `{model_name(item.output)}`，"
        "字段的含义见下方“数据模型”。",
        "",
    ]
    lines += ["### 计算流程", "", "```mermaid", flow_graph(binding), "```", ""]
    lines += [
        "### 步骤明细",
        "",
        "| 序号 | 步骤 | 类型 | 规则 | 代码位置 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, part in enumerate(binding.flow.steps, start=1):
        kind = STEP_KIND_TEXT.get(part.kind, part.kind)
        values = [index, part.title, kind, part.rule or "", location_text(part)]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines += ["", "### 字段来源", "", "每个输出字段是哪一步写下的、用了哪些输入。", ""]
    lines += [
        "| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source in field_sources(binding).values():
        values = [source.name, source.meaning, source.origin, source.step]
        values += [source.rule or source.step_rule, "、".join(source.inputs + source.uses)]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]


# 模块操作用到的全部数据模型，包括嵌套的模型，每个只展开一次。
def models_section(items: Iterable[Contract[Any, Any] | Endpoint[Any, Any]]) -> list[str]:
    models: list[type[BaseModel]] = []
    for item in items:
        collect(item.input, models)
        collect(item.output, models)
    lines = ["## 数据模型", ""]
    for model in models:
        lines += [f"### {model_name(model)}", "", *field_table(model), ""]
    return lines


# 按出现顺序收集一个模型及其字段中嵌套的模型。
def collect(model: type[BaseModel], found: list[type[BaseModel]]) -> None:
    if model in found:
        return
    found.append(model)
    for info in model.model_fields.values():
        for inner in nested_models(info.annotation):
            collect(inner, found)


# 从 list[X]、X | None 这类类型标注中找出数据模型。
def nested_models(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [model for arg in get_args(annotation) for model in nested_models(arg)]


# 一个数据模型的字段表。
def field_table(model: type[BaseModel]) -> list[str]:
    lines = [
        "| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    notes = notes_of(model)
    for name, info in model.model_fields.items():
        note = notes.get(name)
        values = [name, type_text(info.annotation), "是" if info.is_required() else "否"]
        values += [note.meaning, note.unit, note.empty, note.rule] if note else ["", "", "", ""]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return lines


# 模块登记的数据表和列。
def tables_section(tables: tuple[Table, ...]) -> list[str]:
    if not tables:
        return []
    lines = ["## 数据表", ""]
    for table in tables:
        lines += [
            f"### {table.name}",
            "",
            "| 列 | 类型 | 可空 | 主键 | 索引 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for column in table.columns:
            indexed = "唯一" if column.unique else ("是" if column.index else "")
            values = [column.name, str(column.type), yes(column.nullable), yes(column.primary_key)]
            lines.append("| " + " | ".join(cell(value) for value in values + [indexed]) + " |")
        lines.append("")
    return lines


# 数据模型的显示名，泛型写成 Page[ProductView]。
def model_name(model: type[BaseModel]) -> str:
    return type_text(model)


# 把类型标注整理成简短可读的文字。
def type_text(annotation: Any) -> str:
    text = getattr(annotation, "__name__", None) if isinstance(annotation, type) else None
    text = text or str(annotation)
    return strip_modules(text).replace("typing.", "")


# 去掉类型文字中的包路径，只留类名。
def strip_modules(text: str) -> str:
    return re.sub(r"\b(?:[a-z_][\w]*\.)+([A-Za-z_]\w*)", r"\1", text)


# 布尔值写成“是”或空。
def yes(value: object) -> str:
    return "是" if value else ""


# 整理表格单元格。
def cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


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
            model_name(endpoint.input),
            model_name(endpoint.output),
            str(endpoint.unknown_on),
            str(endpoint.accepted_statuses),
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]
