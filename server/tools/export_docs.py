"""
从代码中的声明生成文档，不启动服务、不连接数据库：
- out/api/openapi.json 与 out/api/index.md：接口清单；
- doc/modules.md：模块关系图；doc/模块名/flows.md：每个操作的输入输出、流程图和字段来源。
用法：uv run python -m tools.export_docs；加 --check 只比较不写入，文档过期时返回非零。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.setup.catalog import MODULES
from shared.data.fields import notes_of
from shared.graphs.lineage import field_sources
from shared.graphs.static import flow_graph, module_graph
from shared.modules.catalog import Binding, Catalog
from tools.api_doc import api_markdown
from tools.quality.rules import PROJECT, ROOT

HEADER = (
    "> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；"
    "业务含义写在 needs.md 和 rules.md。"
)


# 把类型标注整理成简短可读的文字。
def type_text(annotation: Any) -> str:
    text = getattr(annotation, "__name__", None) if isinstance(annotation, type) else None
    text = text or str(annotation)
    return re.sub(r"\b(?:[a-z_][\w]*\.)+([A-Za-z_]\w*)", r"\1", text).replace("typing.", "")


# 生成一个数据类型的字段表。
def field_table(model: type[BaseModel]) -> list[str]:
    lines = [
        "| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, note in notes_of(model).items():
        info = model.model_fields[name]
        values = [name, type_text(info.annotation), "是" if info.is_required() else "否"]
        values += [note.meaning, note.unit, note.empty, note.rule]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return lines


# 生成一个操作的章节：输入输出、流程图、字段来源。
def contract_section(binding: Binding) -> list[str]:
    item = binding.contract
    lines = [f"## {item.title}（{item.name}）", ""]
    lines += [f"输入 `{item.input.__name__}`：", "", *field_table(item.input), ""]
    lines += [f"输出 `{item.output.__name__}`：", "", *field_table(item.output), ""]
    lines += ["计算流程：", "", "```mermaid", flow_graph(binding), "```", ""]
    lines += [
        "字段来源：",
        "",
        "| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source in field_sources(binding).values():
        values = [
            source.name,
            source.meaning,
            source.origin,
            source.step,
            source.rule or source.step_rule,
        ]
        values.append("、".join(source.inputs + source.uses))
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]


# 生成一个模块的 flows.md 全文。
def module_doc(catalog: Catalog, name: str) -> str:
    module = catalog.modules[name]
    links = catalog.links().get(name, {})
    depends = (
        "、".join(f"{target}（{'、'.join(titles)}）" for target, titles in links.items()) or "无"
    )
    lines = [
        f"# {module.title}：操作与流程",
        "",
        HEADER,
        "",
        f"模块 `{name}`，版本 {module.version}。调用的其他模块：{depends}。",
        "",
    ]
    lines += [
        "## 公开操作",
        "",
        "| 操作 | 名称 | 权限 | 调用方式 | 可能的业务错误 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in module.provides:
        way = "接口或任务" if item.entry else "只供其他模块调用"
        errors = "、".join(f"{error.code}（{error.message}）" for error in item.errors) or "无"
        lines.append(f"| {item.action} | {item.title} | {item.access} | {way} | {cell(errors)} |")
    lines.append("")
    for item in module.provides:
        lines += contract_section(catalog.bindings[item])
    return "\n".join(lines).rstrip() + "\n"


# 生成 doc/modules.md：全部模块和它们之间的调用关系。
def modules_doc(catalog: Catalog) -> str:
    lines = ["# 模块关系", "", HEADER.replace("needs.md 和 rules.md", "各模块目录"), ""]
    lines += ["| 模块 | 名称 | 版本 | 业务文档 |", "| --- | --- | --- | --- |"]
    for module in catalog.modules.values():
        link = f"[{module.name}/]({module.name}/)"
        lines.append(f"| {module.name} | {module.title} | {module.version} | {link} |")
    lines += ["", "```mermaid", module_graph(catalog), "```", ""]
    return "\n".join(lines)


# 列出全部应生成的文档及其内容。
def generated(catalog: Catalog) -> dict[Path, str]:
    files = {PROJECT / "doc" / "modules.md": modules_doc(catalog)}
    for name, module in catalog.modules.items():
        files[PROJECT / module.doc / "flows.md"] = module_doc(catalog, name)
    return files


# 找出内容已过期的生成文档。
def outdated(catalog: Catalog) -> list[Path]:
    return [
        path
        for path, text in generated(catalog).items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]


# 整理表格单元格。
def cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


# 写入全部文档；check 为真时只比较。
def main() -> None:
    parser = argparse.ArgumentParser(description="从声明生成接口文档和模块流程文档")
    parser.add_argument("--check", action="store_true", help="只检查文档是否过期，不写入")
    args = parser.parse_args()
    catalog = Catalog(MODULES)
    if args.check:
        stale = outdated(catalog)
        for path in stale:
            print(f"文档已过期：{path.relative_to(PROJECT)}")
        sys.exit(1 if stale else 0)
    for path, text in generated(catalog).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    api = ROOT / "out" / "api"
    api.mkdir(parents=True, exist_ok=True)
    schema, markdown = api_markdown()
    (api / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (api / "index.md").write_text(markdown, encoding="utf-8")
    print(f"已生成 {len(generated(catalog))} 份模块文档和 out/api 下的接口文档")


if __name__ == "__main__":
    main()
