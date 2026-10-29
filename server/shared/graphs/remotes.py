from shared.records.models import RunRecord
from shared.records.summary import duration


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
                call.endpoint or call.remote,
                call.status or "未知",
                call.outcome,
                duration(call.elapsed_ms),
                "；".join(f"{name}: {problem}" for name, problem in call.fields.items()),
            ]
            lines.append("| " + " | ".join(safe_cell(value) for value in values) + " |")
    return lines


def safe_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
