"""
从声明生成两种静态图：模块关系图（谁调用谁）和计算流程图（一个操作按什么顺序执行哪些步骤）。
静态图只说明允许和计划的关系，实际走了哪条路要看运行记录生成的执行图。
图上的节点只放序号和业务标题，让看图的人一眼跟上流程；规则、函数位置、读写的字段
这类细节放在文档里图下方的表格中，两边各做各的事。
"""

from typing import Any

from shared.data.fields import notes_of
from shared.db.budget import DEFAULT_BUDGET
from shared.graphs.imports import import_plan_lines
from shared.graphs.mermaid import STYLES, label, node_id
from shared.modules.catalog import Binding, Catalog
from shared.pipelines.plan import FanOut, Pipeline, Wait


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


# 把查询额度写成一句话，供图上的额度节点使用。
def budget_sentence(budget: Any) -> str:
    source = "（默认值，操作没有单独声明）" if budget is None else ""
    data = budget or DEFAULT_BUDGET
    content = round(data.bytes / 1_000_000)
    return (
        f"查询额度{source}：最多 {data.queries} 次查询、{data.rows} 行结果、"
        f"{content} MB 返回内容、同一存储函数最多调用 {data.repeated} 次"
    )


# 生成一个操作的计算流程图：输入、各步骤、条件、调用和结果。
# 节点只有序号和标题，步骤类型用颜色区分（图例在文档里图下方）。
def flow_graph(binding: Binding, execution: dict[str, Any] | None = None) -> str:
    for pipeline in binding.module.pipelines:
        if pipeline.start is binding.contract:
            return pipeline_operation_graph(pipeline, binding)
    flow, item = binding.flow, binding.contract
    result_note = binding.types.notes[flow.result]
    lines, previous = operation_start(binding)
    if any(plan.contract is item and plan.segmented for plan in binding.module.jobs):
        lines += ['    batch["分段任务：每批独立保存，按游标从断点继续"]']
        lines.append(f"    {previous} --> batch")
        previous = "batch"
    for index, part in enumerate(flow.steps, start=1):
        current = f"s{index}"
        record = execution.get(part.name) if execution is not None else None
        detail = execution_text(record) if execution is not None else ""
        style = record["status"] if record else part.kind
        # call 是 Mermaid 的语法关键字；业务种类保持不变，仅转换图中样式名。
        style = "invoke" if style == "call" else style
        lines.append(f'    {current}["{index}. {label(part.title)}{detail}"]:::{style}')
        edge = f' -->|"条件：{label(part.when.title)}"| ' if part.when else " --> "
        lines.append(f"    {previous}{edge}{current}")
        lines += call_lines(current, part.uses, part.prompts)
        for endpoint in part.endpoints:
            target = node_id("e", endpoint.name)
            text = label(f"上游接口：{endpoint.name}（{endpoint.method}，{endpoint.effect}）")
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


# 同一测试运行的状态可以叠在计算图上：节点补一行上次测试的结果。
# 产出字段等明细不进图，需要时看 dev status --operation 的表格输出。
def execution_text(record: dict[str, Any] | None) -> str:
    if record is None:
        return "<br/>上次测试没有执行这一步"
    elapsed = record.get("elapsed_ms")
    time = f"{elapsed:.0f} 毫秒" if elapsed is not None else "用时未知"
    return f"<br/>上次测试：{label(record['status'])} · {time}"


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


# 把秒数写成便于阅读的时长。
def seconds_text(value: Any) -> str:
    seconds = int(value)
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds / 60:g} 分钟"
    hours, minutes = divmod(seconds, 3600)
    return f"{hours} 小时" + (f"{minutes:g} 分钟" if minutes else "")


# 多阶段声明图连接公开操作，等待节点写明检查间隔和最长等待时间。
def pipeline_graph(pipeline: Pipeline) -> str:
    lines = ["flowchart LR", '  start["定时启动 / 周期内不重复"]']
    previous = "start"
    for index, stage in enumerate(pipeline.stages):
        text = f"{stage.name}：{stage.operation.name}"
        if isinstance(stage, Wait):
            text += f"；每{seconds_text(stage.every)}检查一次，最多等{seconds_text(stage.timeout)}"
        lines.append(f'  s{index}["{label(text)}"]')
        lines.append(f"  {previous} --> s{index}")
        if isinstance(stage, FanOut):
            join = type(stage.join).__name__
            text = f"{join}汇合；成员同时最多 {stage.max_parallel} 个"
            lines.append(f'  s{index} --> g{index}["{text}"]')
            for child_index, child in enumerate(stage.stages):
                text = label(f"{child.name}：{child.operation.name}")
                lines.append(f'  s{index} -.-> c{index}_{child_index}["{text}"]')
        previous = f"s{index}"
    return "\n".join(lines)


# 多阶段入口仍是公开操作，流程图同时附上该入口的额度说明。
def pipeline_operation_graph(pipeline: Pipeline, binding: Binding) -> str:
    text = label(budget_sentence(binding.contract.query_budget), limit=None)
    return pipeline_graph(pipeline) + f'\n  budget["{text}"]\n  start -.-> budget'


# 输入节点列出输入字段的含义；额度单独一个节点，写成一句话。
def operation_start(binding: Binding) -> tuple[list[str], str]:
    item = binding.contract
    notes = notes_of(item.input)
    inputs = "、".join(note.meaning or name for name, note in notes.items()) or "无"
    aliases = "、".join(item.aliases)
    alias_text = f"<br/>业务别名：{label(aliases)}" if aliases else ""
    lines = ["flowchart TD", f'    start(["输入：{label(inputs)}{alias_text}"])']
    text = label(budget_sentence(item.query_budget), limit=None)
    lines += [f'    budget["{text}"]', "    start --> budget"]
    return lines, "budget"
