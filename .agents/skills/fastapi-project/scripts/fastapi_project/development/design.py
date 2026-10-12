"""
生成可提交的项目设计与结构进度，始终不读取本机检查历史或数据库。
机器上的实际测试与运行状态由 fastapi_project.project 即时输出，避免进入通用模板。
"""

from pathlib import Path

from fastapi_docs.progress_doc import cell
from fastapi_project.development.plan import read_plan

from shared.graphs.mermaid import label, node_id
from shared.graphs.static import module_graph
from shared.modules.catalog import Catalog
from shared.modules.libraries import library_links, library_specs


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
            count = f"{registered}/{len(targets)}" if targets else "操作尚未定义"
            text = f"{package['title']}：登记 {count}"
            graph += [f'    {child}["{label(text)}"]', f"    {parent} --> {child}"]
            values = [
                line["name"],
                module,
                count,
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
    graph += library_graph(project / "server")
    return design_text(graph, rows)


# 工具与实际调用者从静态导入生成，不把计划依赖当作已经连接的代码。
def library_graph(root: Path) -> list[str]:
    specs = library_specs(root)
    names = {spec.name for spec in specs}
    graph = [f'    {node_id("m", spec.name)}["工具：{label(spec.title)}"]' for spec in specs]
    for source, targets in sorted(library_links(root).items()):
        for target in targets:
            if target in names:
                graph.append(f'    {node_id("m", source)} -->|"纯工具"| {node_id("m", target)}')
    return graph


# 自动生成说明只包含静态信息，实际测试状态留在机器上的检查记录中。
def design_text(graph: list[str], rows: list[str]) -> str:
    return "\n".join(
        [
            "# 项目设计与结构进度",
            "",
            "> 这份文件由 fastapi_docs.export_docs 生成。计划来自 project-plan.json，",
            "> 登记数量来自代码。登记了多少个操作只说明代码里有了它们，不代表测试通过。",
            "",
            "下面几条命令用来看项目的实际状态：",
            "",
            "- 看全项目摘要：`uv run python ../.agents/skills/fastapi-project/scripts/"
            "run_project.py project --summary --json`",
            "- 看一个业务包：`uv run python ../.agents/skills/fastapi-project/scripts/"
            "run_project.py project --module 模块名 --summary --json`",
            "- 看一个操作的步骤和证据：`uv run python ../.agents/skills/fastapi-project/scripts/"
            "run_project.py project --operation 模块.操作 --json`",
            "- 看改动会影响哪些调用方：`uv run python ../.agents/skills/fastapi-project/scripts/"
            "run_project.py impact --base origin/main --json`",
            "",
            "完整的 JSON 仍然保留，需要时再读取。局部检查不能代替完整检查；",
            "登记和测试执行也不等于业务验收，这三件事要分别确认。",
            "",
            "```mermaid",
            *graph,
            "```",
            "",
            "| 业务线 | 开发包 | 已登记/计划操作 | 尚未登记 |",
            "| --- | --- | --- | --- |",
            *(
                rows
                or [
                    "还没有在 project-plan.json 里填写业务线和开发包；填写之后，"
                    "这里会显示每个包的计划和登记进度。",
                ]
            ),
            "",
        ]
    )
