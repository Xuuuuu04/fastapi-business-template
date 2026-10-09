"""
上游接口的中文运行报告表，字段错误只包含受控路径和错误类别。
"""

from shared.records.models import RunRecord
from shared.records.summary import duration


# 协议状态与有限字段问题进入中文报告，不复制上游取值。
def remote_table(run: RunRecord) -> list[str]:
    if not any(step.remotes for step in run.steps):
        return []
    lines = [
        "",
        "| 步骤 | 上游接口 | HTTP | 结果 | 耗时 | 字段问题 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for step in run.steps:
        for call in step.remotes:
            values = [
                step.title,
                call.endpoint or "未知（旧调用）",
                call.status or "未知",
                call.outcome,
                duration(call.elapsed_ms),
                "；".join(f"{name}: {problem}" for name, problem in call.fields.items()),
            ]
            lines.append("| " + " | ".join(safe_cell(value) for value in values) + " |")
    return lines


# 表格文字转义，不把上游字段路径当作Markdown。
def safe_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
