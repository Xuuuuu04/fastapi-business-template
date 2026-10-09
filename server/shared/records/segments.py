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
        + (f" · 导入对账{run.import_report.get('status', '未知')}" if run.import_report else "")
    )


# 提醒超出退出等待预算的批次，不改变提交、停止或恢复行为。
def warn_slow_batch(run: RunRecord) -> None:
    budget = run.segment_shutdown_seconds
    if not run.segment_number or budget is None or run.elapsed_ms <= budget * 1000:
        return
    run.segment_warning = (
        f"本批用时{run.elapsed_ms / 1000:.3f}秒，超过 worker 退出等待时间"
        f"（job_shutdown_seconds={budget:g}秒）；建议缩小批次，"
        "或同步调整部署停止宽限，避免部署强杀后重做未提交批次"
    )
