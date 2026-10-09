"""
步骤节点与纯计算引用的图展示，声明和实际步骤耗时分别保留。
"""

from shared.flow.step import Step, source_of
from shared.graphs.mermaid import label
from shared.records.models import STEP_STATUS_TEXT, StepRecord
from shared.records.summary import duration


# 计算图显示步骤及其纯计算函数位置，实际耗时由所属步骤记录。
def declaration_location(part: Step) -> str:
    text = f"<br/>{label(part.name)} · {label(part.source, limit=None)}"
    return text + "".join(
        f"<br/>纯计算：{label(func.__name__ + ' · ' + source_of(func), limit=None)}"
        for func in part.calcs
    )


# 位置和产出直接写在节点中；完整字段形状保留在结构化记录中。
def step_node(node: str, index: int, step: StepRecord) -> list[str]:
    status = STEP_STATUS_TEXT.get(step.status, step.status)
    parts = [
        f"{index}. {step.title} | {status} | {duration(step.elapsed_ms)}",
        step.name,
        step.error_place or step.source,
    ]
    text = "<br/>".join(label(part, limit=None) for part in parts)
    outputs = "、".join(step.outputs) or "无"
    text += (
        f"<br/>产出 {len(step.outputs)}/{len(step.writes)}：{label(outputs)}"
        if step.outputs_recorded
        else "<br/>产出未知（旧记录）"
    )
    calcs = "、".join(step.calcs) if step.calcs is not None else "未知（旧记录）"
    if calcs:
        text += f"<br/>声明纯计算：{label(calcs, limit=None)}；耗时计入本步骤"
    if step.error_code:
        text += f"<br/>错误：{label(step.error_code)}"
    return [f'        {node}["{text}"]:::{step.status}']
