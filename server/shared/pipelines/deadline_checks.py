from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.pipelines.plan import Pipeline


def check_deadline(pipeline: Pipeline) -> list[str]:
    problems = []
    if pipeline.on_overdue not in ("continue", "pause"):
        problems.append(f"流程 {pipeline.name} 的 on_overdue 只能是 continue 或 pause")
    point = pipeline.complete_by
    if point is None:
        return problems
    if not isinstance(point.at, time) or point.at.tzinfo is not None:
        problems.append(
            f"流程 {pipeline.name} 的 complete_by 必须是当地时间 time，不带时区；时区通过 zone 指定"
        )
    if type(point.days_after) is not int or not 0 <= point.days_after <= 366:
        problems.append(f"流程 {pipeline.name} 的 days_after 必须是 0 到 366 之间的整数")
    try:
        ZoneInfo(point.zone)
    except (ZoneInfoNotFoundError, ValueError):
        problems.append(f"流程 {pipeline.name} 的 complete_by 时区无法识别")
    return problems
