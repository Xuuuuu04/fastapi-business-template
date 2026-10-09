"""
从声明生成两种静态图：模块关系图（谁调用谁）和计算流程图（一个操作按什么顺序执行哪些步骤）。
静态图只说明允许和计划的关系，实际走了哪条路要看运行记录生成的执行图。
"""

from dataclasses import asdict
from typing import Any

from shared.data.fields import notes_of
from shared.db.budget import DEFAULT_BUDGET
from shared.graphs.imports import import_plan_lines
from shared.graphs.mermaid import STYLES, label, node_id
from shared.graphs.steps import declaration_location
from shared.modules.catalog import Binding, Catalog
from shared.pipelines.plan import FanOut, Pipeline, Wait
from shared.records.models import STEP_KIND_TEXT


# 生成模块关系图：说明模块经由哪些操作调用其他模块。
def module_graph(catalog: Catalog) -> str:
    lines = ["flowchart LR"]
    for module in catalog.modules.values():
        aliases = f"；别名：{'、'.join(module.aliases)}" if module.aliases else ""
        text = label(f"{module.title}（{module.name}，版本 {module.version}）{aliases}")
        lines.append(f'    {node_id("m", module.name)}["{text}"]')
    for source, targets in catalog.links().items():
        for target, titles in targets.items():
            via = label("、".join(titles))
            lines.append(f'    {node_id("m", source)} -->|"{via}"| {node_id("m", target)}')
    return "\n".join(lines)


# 生成一个操作的计算流程图：输入、各步骤、条件、调用和结果。
def flow_graph(binding: Binding, execution: dict[str, Any] | None = None) -> str:
    for pipeline in binding.module.pipelines:
        if pipeline.start is binding.contract:
            return pipeline_operation_graph(pipeline, binding)
    flow, item = binding.flow, binding.contract
    result_note = binding.types.notes[flow.result]
    lines, previous = operation_start(binding)
    if any(plan.contract is item and plan.segmented for plan in binding.module.jobs):
        lines += ['    batch["分段任务：每批独立事务，按游标恢复"]', f"    {previous} --> batch"]
        previous = "batch"
    for index, part in enumerate(flow.steps, start=1):
        current = f"s{index}"
        rule = f"<br/>规则 {label(part.rule)}" if part.rule else ""
        kind = STEP_KIND_TEXT.get(part.kind, part.kind)
        location = declaration_location(part)
        fields = (
            f"<br/>读：{label('、'.join(part.reads) or '无')} → "
            f"写：{label('、'.join(part.writes) or '无')}"
        )
        record = execution.get(part.name) if execution is not None else None
        detail = execution_text(record) if execution is not None else ""
        style = record["status"] if record else part.kind
        # call 是 Mermaid 的语法关键字；业务种类保持不变，仅转换图中样式名。
        style = "invoke" if style == "call" else style
        lines.append(
            f'    {current}["{index}. {label(part.title)}（{kind}）'
            f'{rule}{location}{fields}{detail}"]:::{style}'
        )
        edge = f' -->|"条件：{label(part.when.title)}"| ' if part.when else " --> "
        lines.append(f"    {previous}{edge}{current}")
        lines += call_lines(current, part.uses, part.prompts)
        for endpoint in part.endpoints:
            target = node_id("e", endpoint.name)
            text = label(f"上游接口：{endpoint.name} · {endpoint.method} · {endpoint.effect}")
            lines += [f'    {target}[["{text}"]]', f"    {current} -.-> {target}"]
        for task in part.later:
            target = node_id("j", task.name)
            lines.append(f'    {target}[["后台任务：{label(task.title)}"]]')
            lines.append(f"    {current} -.-> {target}")
        previous = current
    additions, previous = import_plan_lines(binding, previous)
    lines += additions
    lines.append(f'    finish(["结果：{label(result_note.meaning or flow.result)}"])')
    lines.append(f"    {previous} --> finish")
    return "\n".join(lines + STYLES)


# 同一测试运行的状态可以直接叠在计算图上，未经过的节点保持明确。
def execution_text(record: dict[str, Any] | None) -> str:
    if record is None:
        return "<br/>该运行未执行"
    elapsed = record.get("elapsed_ms")
    text = f"{elapsed:.2f} ms" if elapsed is not None else "耗时未知"
    outputs = record.get("outputs", {})
    produced = "、".join(outputs) if record.get("outputs_recorded") else "未知"
    return f"<br/>最近测试：{label(record['status'])} · {text}<br/>产出：{label(produced or '无')}"


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


# 多阶段声明图连接公开操作，等待检查明确展示间隔和最长时限。
def pipeline_graph(pipeline: Pipeline) -> str:
    lines = ["flowchart LR", '  start["定时 / 周期去重"]']
    previous = "start"
    for index, stage in enumerate(pipeline.stages):
        text = f"{stage.name}：{stage.operation.name}"
        if isinstance(stage, Wait):
            text += f"；每{stage.every}s检查，最长{stage.timeout}s"
        lines.append(f'  s{index}["{label(text)}"]')
        lines.append(f"  {previous} --> s{index}")
        if isinstance(stage, FanOut):
            text = f"{type(stage.join).__name__}汇合；成员并发≤{stage.max_parallel}"
            lines.append(f'  s{index} --> g{index}["{text}"]')
            for child_index, child in enumerate(stage.stages):
                text = label(f"{child.name}：{child.operation.name}")
                lines.append(f'  s{index} -.-> c{index}_{child_index}["{text}"]')
        previous = f"s{index}"
    return "\n".join(lines)


# 多阶段入口仍是公开操作，流程图同时附上该入口的额度声明。
def pipeline_operation_graph(pipeline: Pipeline, binding: Binding) -> str:
    text = label(f"查询额度：{asdict(binding.contract.query_budget or DEFAULT_BUDGET)}", limit=None)
    return pipeline_graph(pipeline) + f'\n  budget["{text}"]\n  start -.-> budget'


# 输入含义、业务别名和额度来自同一个约定，不伪装成业务计算步骤。
def operation_start(binding: Binding) -> tuple[list[str], str]:
    item = binding.contract
    notes = notes_of(item.input)
    inputs = "、".join(note.meaning or name for name, note in notes.items()) or "无"
    aliases = "、".join(item.aliases)
    alias_text = f"<br/>业务别名：{label(aliases)}" if aliases else ""
    lines = ["flowchart TD", f'    start(["输入：{label(inputs)}{alias_text}"])']
    text = label(f"查询额度：{asdict(item.query_budget or DEFAULT_BUDGET)}", limit=None)
    lines += [f'    budget["{text}"]', "    start --> budget"]
    return lines, "budget"
