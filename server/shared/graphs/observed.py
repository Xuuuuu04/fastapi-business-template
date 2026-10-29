import json

from shared.db.budget import budget_text
from shared.graphs.database import database_nodes
from shared.graphs.imports import import_node, report_header
from shared.graphs.mermaid import MAX_LABEL, STYLES, label
from shared.graphs.remotes import remote_table
from shared.graphs.steps import step_node
from shared.records.models import (
    RUN_STATUS_TEXT,
    STEP_KIND_TEXT,
    STEP_STATUS_TEXT,
    WRITES_TEXT,
    RunRecord,
    StepRecord,
)
from shared.records.segments import segment_text
from shared.records.summary import duration


def run_graph(runs: list[RunRecord]) -> str:
    lines = ["flowchart TD"]
    entries = {run.id: f"entry_{run.id}" for run in runs}
    for run in runs:
        state = RUN_STATUS_TEXT.get(run.status, run.status)
        aliases = "、".join(run.aliases) if run.aliases is not None else "未知（旧记录）"
        lines.append(f'    subgraph run_{run.id}["{label(run.title)}（{state}）"]')
        entry = entries[run.id]
        text = label(
            f"{run.contract} · {duration(run.elapsed_ms)}"
            + segment_text(run)
            + (f" · 业务别名：{aliases}" if aliases else ""),
            limit=None if run.segment_number else MAX_LABEL,
        )
        style = run.status if run.status in ("ok", "running") else "failed"
        lines.append(f'        {entry}["{text}"]:::{style}')
        text = label(budget_text(run.query_budget), limit=None)
        lines += [f'        {entry}_budget["{text}"]', f"        {entry} -.-> {entry}_budget"]
        previous = entry
        for index, step in enumerate(run.steps, start=1):
            node = f"n_{run.id}_{index}"
            lines += condition_node(node, previous, step)
            lines += step_node(node, index, step)
            lines.append(
                f"        {previous if not step.condition else node + '_condition'} --> {node}"
            )
            lines += database_nodes(node, step)
            lines += external_nodes(node, step)
            previous = node
        lines += import_node(run, previous)
        lines.append("    end")
    for run in runs:
        for index, step in enumerate(run.steps, start=1):
            for child in step.children:
                if child in entries:
                    lines.append(f"    n_{run.id}_{index} -.-> {entries[child]}")
    return "\n".join(lines + STYLES)


def condition_node(node: str, previous: str, step: StepRecord) -> list[str]:
    if not step.condition:
        return []
    result = {True: "执行", False: "跳过", None: "未知"}[step.condition_result]
    parts = [
        step.condition,
        f"{result} · {duration(step.condition_elapsed_ms)}",
        step.condition_name,
        step.condition_source,
    ]
    text = "<br/>".join(label(part, limit=None) for part in parts)
    return [f'        {node}_condition{{"{text}"}}', f"        {previous} --> {node}_condition"]


def external_nodes(node: str, step: StepRecord) -> list[str]:
    calls = [(call.prompt, call.status, call.elapsed_ms) for call in step.models]
    calls += [
        (
            (call.endpoint or call.remote + "（接口未知）") + f" · {call.outcome}",
            "failed"
            if call.error or call.status >= 400
            else "running"
            if call.status == 0
            else "ok",
            call.elapsed_ms,
        )
        for call in step.remotes
    ]
    lines = []
    for index, (name, status, elapsed) in enumerate(calls, start=1):
        target = f"{node}_external{index}"
        text = label(f"{name} · {status} · {duration(elapsed)}")
        lines += [f'        {target}["{text}"]:::{status}', f"        {node} -.-> {target}"]
    return lines


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
        "2. 对照字段说明和这个操作的测试样例，确认预期结果。",
        "3. 再读取出错位置附近的源码和对应测试；未知的信息继续查证，不要假设。",
    ]
    return "\n".join(lines)


def error_text(run: RunRecord) -> str:
    if not run.error_code:
        return "无"
    if run.error_message.startswith(run.error_code):
        return run.error_message
    return f"{run.error_code}：{run.error_message}"


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
    if run.segment_number:
        rows.append(("分段", segment_text(run).strip(" ·")))
        rows.append(("恢复游标", json.dumps(run.segment_cursor, ensure_ascii=False)))

    if run.gaps:
        rows.append(("记录完整性", "；".join(run.gaps)))
    if run.steps:
        slowest = max(run.steps, key=lambda step: step.elapsed_ms)
        rows.append(
            (
                "最长步骤",
                f"{slowest.title} · {duration(slowest.elapsed_ms)} · "
                f"{slowest.source} · {slowest.name}",
            )
        )
    return [
        "| 项目 | 内容 |",
        "| --- | --- |",
        *[f"| {key} | {cell(value)} |" for key, value in rows],
        "",
    ]


def run_section(run: RunRecord, is_root: bool) -> list[str]:
    lines = report_header(run, is_root)
    if not is_root:
        lines += [run.summary, ""]
    lines += ["| 序号 | 步骤 | 类型 | 状态 | 耗时 | 写入 | 说明 | 位置 |"]
    lines += ["| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for index, step in enumerate(run.steps, start=1):
        lines.append(step_row(index, step))
    lines += ["", budget_text(run.query_budget)]
    lines += database_table(run)
    lines += remote_table(run)
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


def step_row(index: int, step: StepRecord) -> str:
    status = STEP_STATUS_TEXT.get(step.status, step.status)
    if step.condition:
        status += f"（条件：{step.condition}）"
    notes = list(step.notes)
    if step.condition:
        notes.append(
            f"条件 {step.condition_name}：{step.condition_result}，"
            f"{duration(step.condition_elapsed_ms)}，{step.condition_source}"
        )
    if step.error_message:
        notes.insert(0, f"错误：{step.error_message}")
    place = step.error_place or step.source
    values = [index, step.title, STEP_KIND_TEXT.get(step.kind, step.kind), status]
    values += [
        duration(step.elapsed_ms),
        (f"产出 {len(step.outputs)}/{len(step.writes)}；" if step.outputs_recorded else "")
        + "；".join(step.values),
        "；".join(notes),
        f"{place} · {step.name}",
    ]
    return "| " + " | ".join(cell(value) for value in values) + " |"


def database_table(run: RunRecord) -> list[str]:
    if not any(step.database_count for step in run.steps):
        return []
    lines = [
        "",
        "| 步骤 | 数据库调用 | 表或视图 | 状态 | 耗时 | 行数 | 函数与位置 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    summaries = []
    for step in run.steps:
        for call in step.database:
            values = [
                step.title,
                f"{call.target}.{call.method} ({call.statement})",
                ", ".join(call.tables) or "未知",
                call.status,
                duration(call.elapsed_ms),
                call.rows,
                f"{call.source} · {call.function}",
            ]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
        if step.database_count:
            summaries.append(
                f"\n{cell(step.title)}：SQL 共 {step.database_count} 次，"
                f"合计 {duration(step.database_elapsed_ms)}，保留 {len(step.database)} 次细节。"
            )
    return lines + summaries


def cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
