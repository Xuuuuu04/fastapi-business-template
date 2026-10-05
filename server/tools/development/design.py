"""
生成可提交的项目设计与结构进度，始终不读取本机检查历史或数据库。
机器上的实际测试与运行状态由 tools.project 即时输出，避免进入通用模板。
"""

from pathlib import Path

from shared.graphs.mermaid import label, node_id
from shared.graphs.static import module_graph
from shared.modules.catalog import Catalog
from tools.development.plan import read_plan
from tools.progress_doc import cell


# 从根节点生成业务线与模块图，并逐项列出还没有登记的目标操作。
def design_doc(catalog: Catalog, project: Path) -> str:
    plan = read_plan(project)
    name = plan["name"] if plan else project.name
    graph = ["flowchart TD", f'    root["{label(name)}"]']
    rows = []
    planned: set[str] = set()
    for index, line in enumerate(plan["lines"] if plan else []):
        parent = f"line{index}"
        graph += [f'    {parent}["{label(line["name"])}"]', f"    root --> {parent}"]
        for package in line["packages"]:
            module = package["module"]
            planned.add(module)
            targets = [f"{module}.{operation}" for operation in package["operations"]]
            missing = [operation for operation in targets if operation not in catalog.by_name]
            registered = len(targets) - len(missing)
            child = node_id("m", module)
            text = f"{package['title']}：登记 {registered}/{len(targets)}"
            graph += [f'    {child}["{label(text)}"]', f"    {parent} --> {child}"]
            values = [
                line["name"],
                module,
                f"{registered}/{len(targets)}",
                ", ".join(missing) or "无",
            ]
            rows.append("| " + " | ".join(cell(value) for value in values) + " |")
    for module in catalog.modules.values():
        if module.name not in planned:
            child = node_id("m", module.name)
            graph += [
                f'    {child}["{label(module.title)}（未列入计划）"]',
                f"    root --> {child}",
            ]
    graph += [line for line in module_graph(catalog).splitlines()[1:] if " -->|" in line]
    return design_text(graph, rows)


# 自动生成说明只包含静态信息，实际测试状态留在机器上的检查记录中。
def design_text(graph: list[str], rows: list[str]) -> str:
    return "\n".join(
        [
            "# 项目设计与结构进度",
            "",
            "> 由 tools.export_docs 生成。计划来自 project-plan.json；"
            "登记数量来自代码，不能表示测试通过。",
            "",
            "主代理先读摘要：`uv run python -m tools.project --summary --json`。",
            "单包操作与规则样例："
            "`uv run python -m tools.project --module 模块名 --summary --json`。",
            "单操作步骤与证据：`uv run python -m tools.project --operation 模块.操作 --json`。",
            "修改后的调用方范围：`uv run python -m tools.impact --base origin/main --json`。",
            "完整 JSON 仍保留供按需读取；局部检查不代替全量检查，登记和测试执行不等于业务验收。",
            "",
            "```mermaid",
            *graph,
            "```",
            "",
            "| 业务线 | 开发包 | 已登记/计划操作 | 尚未登记 |",
            "| --- | --- | --- | --- |",
            *(rows or ["尚未填写开发包，完成比例未知。"]),
            "",
        ]
    )
