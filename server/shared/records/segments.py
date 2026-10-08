"""
分段运行图的简短说明，只显示已确认累计数量，长游标在详情中完整显示。
"""

import json

from shared.records.models import RunRecord


# 图只显示已知事实，尚未统计的本批行数保持未知。
def segment_text(run: RunRecord) -> str:
    if not run.segment_number:
        return ""
    rows = "未知" if run.segment_rows is None else str(run.segment_rows)
    state = "已提交" if run.segment_committed else "未确认提交"
    cursor = json.dumps(run.segment_cursor, ensure_ascii=False)
    if len(cursor) > 120:
        cursor = cursor[:120] + "…（完整游标见详情）"
    return (
        f" · 第{run.segment_number}批 · 本批{rows}行"
        f" · 累计{run.segment_total_rows}行 · {state} · 游标{cursor}"
    )
