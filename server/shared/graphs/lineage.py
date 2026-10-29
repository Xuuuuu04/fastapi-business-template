from dataclasses import dataclass, field

from shared.graphs.mermaid import label, node_id
from shared.modules.catalog import Binding


@dataclass
class FieldSource:
    name: str
    meaning: str
    unit: str
    rule: str
    origin: str
    step: str = ""
    step_rule: str = ""
    source: str = ""
    condition: str = ""
    uses: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)


def field_sources(binding: Binding) -> dict[str, FieldSource]:
    notes = binding.types.notes
    input_fields = set(binding.contract.input.model_fields)
    found = {}
    for name, note in notes.items():
        origin = (
            "操作输入" if name in input_fields else ("默认值" if note.has_default else "未写入")
        )
        found[name] = FieldSource(name, note.meaning, note.unit, note.rule, origin)
    for part in binding.flow.steps:
        for name in part.writes:
            source = found[name]
            source.origin, source.step, source.step_rule = "步骤", part.title, part.rule
            source.source, source.inputs = part.source, list(part.reads)
            source.uses = [f"{used.title}（{used.name}）" for used in part.uses]
            source.condition = part.when.title if part.when else ""
    return found


def explain(binding: Binding, name: str, depth: int = 6) -> list[str]:
    sources = field_sources(binding)
    lines: list[str] = []

    def walk(current: str, level: int, seen: set[str]) -> None:
        item = sources.get(current)
        indent = "  " * level
        if item is None:
            lines.append(f"{indent}- {current}：不在流程数据中")
            return
        lines.append(f"{indent}- {describe(item)}")
        if current in seen or level >= depth:
            return
        for inner in item.inputs:
            walk(inner, level + 1, {*seen, current})

    walk(name, 0, set())
    return lines


def describe(item: FieldSource) -> str:
    title = f"{item.meaning or item.name}（{item.name}）"
    if item.origin != "步骤":
        return f"{title}：来自{item.origin}"
    text = f"{title}：由步骤“{item.step}”写入"
    if item.step_rule or item.rule:
        text += f"，规则 {item.rule or item.step_rule}"
    if item.condition:
        text += f"，只在条件“{item.condition}”满足时写入"
    if item.uses:
        text += "，调用 " + "、".join(item.uses)
    if item.inputs:
        text += "，用到 " + "、".join(item.inputs)
    return text + f"；源码 {item.source}"


def lineage_graph(binding: Binding, name: str) -> str:
    sources = field_sources(binding)
    lines = ["flowchart RL"]
    queue, seen = [name], set()
    while queue:
        current = queue.pop(0)
        if current in seen or current not in sources:
            continue
        seen.add(current)
        item = sources[current]
        text = label(f"{item.meaning or current}（{current}）")
        lines.append(f'    {node_id("f", current)}["{text}"]')
        via = (
            label(f"{item.step} {item.rule or item.step_rule}".strip())
            if item.step
            else label(item.origin)
        )
        for inner in item.inputs:
            lines.append(f'    {node_id("f", inner)} -->|"{via}"| {node_id("f", current)}')
            queue.append(inner)
        for used in item.uses:
            target = node_id("c", used)
            lines.append(f'    {target}[["{label(used)}"]] -->|"{via}"| {node_id("f", current)}')
    return "\n".join(lines)
