"""
SQL运行图节点，明细与完整累计分开显示，位置不受细节截断影响。
"""

from shared.graphs.mermaid import label
from shared.records.models import StepRecord
from shared.records.summary import duration


# SQL 节点深入到存储函数和调用行；超出保留数量时标出未保留的细节。
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
            f"大小：{call.bytes if call.bytes is not None else '未知'}",
            f"EXPLAIN：{call.explain_status or '未采集'} {call.explain}",
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
    if missing or not step.database_complete:
        text = f"另 {missing} 次 SQL 仅统计次数和耗时" if missing else "旧记录未采集 SQL 细节"
        lines += [f'        {node}_db_unknown["{text}"]', f"        {node} -.-> {node}_db_unknown"]
    return lines
