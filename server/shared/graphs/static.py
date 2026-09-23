"""
从声明生成两种静态图：模块关系图（谁调用谁）和计算流程图（一个操作按什么顺序执行哪些步骤）。
静态图只说明允许和计划的关系，实际走了哪条路要看运行记录生成的执行图。
"""

from typing import Any

from shared.data.fields import notes_of
from shared.graphs.mermaid import STYLES, label, node_id
from shared.modules.catalog import Binding, Catalog
from shared.records.models import STEP_KIND_TEXT


# 生成模块关系图：每条边说明经由哪些操作调用。
def module_graph(catalog: Catalog) -> str:
    lines = ["flowchart LR"]
    for module in catalog.modules.values():
        text = label(f"{module.title}（{module.name}，版本 {module.version}）")
        lines.append(f'    {node_id("m", module.name)}["{text}"]')
    for source, targets in catalog.links().items():
        for target, titles in targets.items():
            via = label("、".join(titles))
            lines.append(f'    {node_id("m", source)} -->|"{via}"| {node_id("m", target)}')
    return "\n".join(lines)


# 生成一个操作的计算流程图：输入、各步骤、条件、调用和结果。
def flow_graph(binding: Binding) -> str:
    flow, item = binding.flow, binding.contract
    notes = notes_of(item.input)
    inputs = "、".join(note.meaning or name for name, note in notes.items()) or "无"
    result_note = binding.types.notes[flow.result]
    lines = ["flowchart TD", f'    start(["输入：{label(inputs)}"])']
    previous = "start"
    for index, part in enumerate(flow.steps, start=1):
        current = f"s{index}"
        rule = f"<br/>规则 {label(part.rule)}" if part.rule else ""
        kind = STEP_KIND_TEXT.get(part.kind, part.kind)
        lines.append(f'    {current}["{index}. {label(part.title)}（{kind}）{rule}"]:::{part.kind}')
        edge = f' -->|"条件：{label(part.when.title)}"| ' if part.when else " --> "
        lines.append(f"    {previous}{edge}{current}")
        lines += call_lines(current, part.uses, part.prompts)
        previous = current
    lines.append(f'    finish(["结果：{label(result_note.meaning or flow.result)}"])')
    lines.append(f"    {previous} --> finish")
    return "\n".join(lines + STYLES)


# 画出步骤调用的其他操作和使用的提示词。
def call_lines(current: str, uses: tuple[Any, ...], prompts: tuple[Any, ...]) -> list[str]:
    lines = []
    for used in uses:
        target = node_id("c", used.name)
        lines.append(f'    {target}[["调用：{label(used.title)}（{label(used.name)}）"]]')
        lines.append(f"    {current} -.-> {target}")
    for item in prompts:
        target = node_id("p", item.name)
        lines.append(f'    {target}>"提示词：{label(item.title)} v{label(item.version)}"]')
        lines.append(f"    {current} -.-> {target}")
    return lines
