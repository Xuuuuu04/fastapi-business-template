"""
完成时间和逾期策略在启动时验证，不等到定时业务实际执行才发现配置错误。
"""

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.pipelines.plan import Pipeline


# 默认继续符合已有执行行为，显式暂停才停止新批次或新阶段。
def check_deadline(pipeline: Pipeline) -> list[str]:
    problems = []
    if pipeline.on_overdue not in ("continue", "pause"):
        problems.append(f"流程{pipeline.name}on_overdue需要continue或pause")
    point = pipeline.complete_by
    if point is None:
        return problems
    if not isinstance(point.at, time) or point.at.tzinfo is not None:
        problems.append(f"流程{pipeline.name}complete_by需要不带时区的当地time，时区写在zone")
    if type(point.days_after) is not int or not 0 <= point.days_after <= 366:
        problems.append(f"流程{pipeline.name}days_after需要0到366的整数")
    try:
        ZoneInfo(point.zone)
    except (ZoneInfoNotFoundError, ValueError):
        problems.append(f"流程{pipeline.name}complete_by时区无效")
    return problems
