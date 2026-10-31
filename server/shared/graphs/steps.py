from shared.flow.step import Step, source_of
from shared.graphs.mermaid import label
from shared.records.models import STEP_STATUS_TEXT, StepRecord
from shared.records.summary import duration


def location_text(part: Step) -> str:
    text = f"{part.name} · {part.source}"
    for func in part.calcs:
        text += f"；纯计算 {func.__name__} · {source_of(func)}"
    return text


def step_node(node: str, index: int, step: StepRecord) -> list[str]:
    status = STEP_STATUS_TEXT.get(step.status, step.status)
    parts = [f"{index}. {step.title}", f"{status} · {duration(step.elapsed_ms)}"]
    outputs = "、".join(step.outputs) or "无"
    parts.append(f"已写入 {len(step.outputs)}/{len(step.writes)} 个声明字段：{outputs}")
    calcs = "、".join(step.calcs)
    if calcs:
        parts.append(f"计算函数（耗时计入本步骤）：{calcs}")
    if step.error_code:
        parts.append(f"错误：{step.error_code}")
    parts.append(step.error_place or step.source)
    text = "<br/>".join(label(part, limit=None) for part in parts)
    return [f'        {node}["{text}"]:::{step.status}']
