"""
从运行记录生成实际执行图和中文排查报告。
执行图标出每一步完成、失败、跳过的情况和耗时；报告先给中文摘要，再列步骤、字段、调用和源码位置，
供人阅读，也供 Agent 按运行编号直接定位问题，不必从头读代码。
"""

from shared.graphs.mermaid import STYLES, label
from shared.records.models import (
    RUN_STATUS_TEXT,
    STEP_KIND_TEXT,
    STEP_STATUS_TEXT,
    WRITES_TEXT,
    RunRecord,
    StepRecord,
)
from shared.records.summary import duration


# 生成一次运行（含下一层调用）的实际执行图。
def run_graph(runs: list[RunRecord]) -> str:
    lines = ["flowchart TD"]
    first_step: dict[str, str] = {}
    for run in runs:
        state = RUN_STATUS_TEXT.get(run.status, run.status)
        lines.append(f'    subgraph run_{run.id}["{label(run.title)}（{state}）"]')
        previous = ""
        for index, step in enumerate(run.steps, start=1):
            node = f"n_{run.id}_{index}"
            first_step.setdefault(run.id, node)
            status = STEP_STATUS_TEXT.get(step.status, step.status)
            text = f"{index}. {step.title} | {status} | {duration(step.elapsed_ms)}"
            lines.append(f'        {node}["{label(text)}"]:::{step.status}')
            if previous:
                lines.append(f"        {previous} --> {node}")
            previous = node
        lines.append("    end")
    for run in runs:
        for index, step in enumerate(run.steps, start=1):
            for child in step.children:
                if child in first_step:
                    lines.append(f"    n_{run.id}_{index} -.-> {first_step[child]}")
    return "\n".join(lines + STYLES)


# 生成一次运行的中文排查报告（Markdown）。
def run_report(runs: list[RunRecord], root_id: str) -> str:
    by_id = {run.id: run for run in runs}
    root = by_id.get(root_id)
    if root is None:
        return f"没有找到运行编号 {root_id} 的记录。记录可能已过期清理，或者保存时丢失。"
    lines = [f"# 运行报告：{root.title}", "", root.summary, ""]
    lines += info_table(root)
    for run in runs:
        lines += run_section(run, run.id == root.id)
    lines += ["## 实际执行图", "", "```mermaid", run_graph(runs), "```", ""]
    lines += [
        "## 排查建议",
        "",
        "1. 先看失败步骤的错误说明和出错位置。",
        "2. 对照字段说明与模块业务文档中的规则编号，确认预期结果。",
        "3. 再读取出错位置附近的源码和对应测试；未知的信息继续查证，不要假设。",
    ]
    return "\n".join(lines)


# 错误码和说明；说明本身以错误码开头时不再重复。
def error_text(run: RunRecord) -> str:
    if not run.error_code:
        return "无"
    if run.error_message.startswith(run.error_code):
        return run.error_message
    return f"{run.error_code}：{run.error_message}"


# 生成基本信息表。
def info_table(run: RunRecord) -> list[str]:
    rows = [
        ("运行编号", run.id),
        ("操作", f"{run.title}（{run.contract}）"),
        ("状态", RUN_STATUS_TEXT.get(run.status, run.status)),
        ("写入", WRITES_TEXT.get(run.writes, run.writes)),
        ("用时", duration(run.elapsed_ms)),
        ("模块版本", f"{run.module} {run.module_version}"),
        ("代码版本", run.code_version),
        ("请求编号", run.request_id or "无"),
        ("任务编号", run.job_id or "无"),
        ("调用者", run.caller),
        ("错误", error_text(run)),
    ]
    if run.gaps:
        rows.append(("记录完整性", "；".join(run.gaps)))
    return [
        "| 项目 | 内容 |",
        "| --- | --- |",
        *[f"| {key} | {cell(value)} |" for key, value in rows],
        "",
    ]


# 生成一次运行的步骤表和大模型调用表。
def run_section(run: RunRecord, is_root: bool) -> list[str]:
    heading = "## 步骤" if is_root else f"## 下一层：{run.title}（{run.id}）"
    lines = [heading, ""]
    if not is_root:
        lines += [run.summary, ""]
    lines += ["| 序号 | 步骤 | 类型 | 状态 | 耗时 | 规则 | 写入 | 说明 | 位置 |"]
    lines += ["| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for index, step in enumerate(run.steps, start=1):
        lines.append(step_row(index, step))
    models = [(step.title, call) for step in run.steps for call in step.models]
    if models:
        lines += [
            "",
            "| 步骤 | 提示词 | 版本 | 模型 | 状态 | 耗时 | 输入 token | 输出 token | 重试 |",
        ]
        lines += ["| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for title, call in models:
            values: list[object] = [
                title,
                call.prompt,
                call.version,
                call.model,
                call.status,
                duration(call.elapsed_ms),
            ]
            values += [call.input_tokens, call.output_tokens, call.retries]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return [*lines, ""]


# 生成步骤表中的一行。
def step_row(index: int, step: StepRecord) -> str:
    status = STEP_STATUS_TEXT.get(step.status, step.status)
    if step.condition:
        status += f"（条件：{step.condition}）"
    notes = list(step.notes)
    if step.error_message:
        notes.insert(0, f"错误：{step.error_message}")
    place = step.error_place or step.source
    values = [index, step.title, STEP_KIND_TEXT.get(step.kind, step.kind), status]
    values += [
        duration(step.elapsed_ms),
        step.rule or "",
        "；".join(step.values),
        "；".join(notes),
        place,
    ]
    return "| " + " | ".join(cell(value) for value in values) + " |"


# 整理表格单元格，避免破坏 Markdown 表格。
def cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
