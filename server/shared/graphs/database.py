from shared.graphs.mermaid import label
from shared.records.models import StepRecord
from shared.records.summary import duration


def database_nodes(node: str, step: StepRecord) -> list[str]:
    lines = []
    for index, call in enumerate(step.database, start=1):
        current = f"{node}_db{index}"
        parts = [
            f"{call.target}.{call.method} · {call.status} · {duration(call.elapsed_ms)}",
            ", ".join(call.tables) or "表名未知",
            f"行数：{call.rows if call.rows is not None else '未知'}",
            call.function,
            call.source,
        ]
        parts += [
            call.storage_function,
            call.storage_source,
            f"返回内容大小：{call.bytes if call.bytes is not None else '未知'}",
            f"SQL 执行计划（EXPLAIN）：{call.explain_status or '未记录'} {call.explain}",
        ]
        text = "<br/>".join(label(part, limit=None) for part in parts)
        lines += [f'        {current}["{text}"]:::{call.status}', f"        {node} -.-> {current}"]
    for index, (source, counts) in enumerate(step.database_functions.items()):
        text = label(f"{source} · {counts}", limit=None)
        lines += [
            f'        {node}_total{index}["{text}"]',
            f"        {node} -.-> {node}_total{index}",
        ]
    missing = step.database_count - len(step.database)
    if missing:
        text = f"另外 {missing} 次 SQL 只记录了调用次数和耗时"
        lines += [f'        {node}_db_unknown["{text}"]', f"        {node} -.-> {node}_db_unknown"]
    return lines
