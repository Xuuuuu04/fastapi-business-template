"""
步骤节点与纯计算引用的图展示，声明和实际步骤耗时分别保留。
计算图的节点只放序号和标题；函数位置、纯计算这些细节由文档生成器放进图下方的表格。
"""

from shared.flow.step import Step, source_of
from shared.graphs.mermaid import label
from shared.records.models import STEP_STATUS_TEXT, StepRecord
from shared.records.summary import duration


# 步骤在代码中的位置，写成表格单元格里用的纯文本。
def location_text(part: Step) -> str:
    text = f"{part.name} · {part.source}"
    for func in part.calcs:
        text += f"；纯计算 {func.__name__} · {source_of(func)}"
    return text


# 位置和产出直接写在节点中；完整字段形状保留在结构化记录中。
# 节点分行排版：第一行业务标题，之后每行一个信息，不再挤成一长串。
def step_node(node: str, index: int, step: StepRecord) -> list[str]:
    status = STEP_STATUS_TEXT.get(step.status, step.status)
    parts = [f"{index}. {step.title}", f"{status} · {duration(step.elapsed_ms)}"]
    outputs = "、".join(step.outputs) or "无"
    parts.append(
        f"产出 {len(step.outputs)}/{len(step.writes)}：{outputs}"
        if step.outputs_recorded
        else "产出未知（旧记录没有保存）"
    )
    calcs = "、".join(step.calcs) if step.calcs is not None else "未知（旧记录）"
    if calcs:
        parts.append(f"纯计算（耗时算在本步骤内）：{calcs}")
    if step.error_code:
        parts.append(f"错误：{step.error_code}")
    parts.append(step.error_place or step.source)
    text = "<br/>".join(label(part, limit=None) for part in parts)
    return [f'        {node}["{text}"]:::{step.status}']
