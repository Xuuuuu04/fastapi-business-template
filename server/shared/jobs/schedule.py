"""
定时计划：计算每个计划最近一个到期的时段，并以“计划名称加时段”作为请求编号登记任务。
多个 worker 同时计算也只会登记一次；错过的时段按声明跳过（skip）或只补最近一次（latest）。
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from shared.access.caller import SYSTEM
from shared.db.database import Database
from shared.errors.kinds import BusinessError
from shared.jobs.plan import Schedule
from shared.jobs.queue import JobQueue

log = logging.getLogger("server.jobs")

EPOCH = datetime(2000, 1, 1)


# 计算计划在 now 之前（含）最近的一个时段。
def latest_slot(schedule: Schedule, now: datetime) -> datetime:
    zone = ZoneInfo(schedule.zone)
    local = now.astimezone(zone)
    if schedule.every is not None:
        start = EPOCH.replace(tzinfo=zone)
        count = (local - start) // schedule.every
        return start + count * schedule.every
    if schedule.daily_at is None:
        raise ValueError(f"定时计划「{schedule.title}」需要设置 every 或 daily_at")
    today = datetime.combine(local.date(), schedule.daily_at, tzinfo=zone)
    return today if today <= local else today - timedelta(days=1)


class Scheduler:
    # 记住每个计划上一次处理的时段，避免同一进程反复登记。
    def __init__(self, schedules: list[Schedule], queue: JobQueue, database: Database) -> None:
        self.schedules = schedules
        self.queue = queue
        self.database = database
        self.last: dict[str, datetime] = {}

    # 检查全部计划，为新到期的时段登记任务；返回本次登记的数量。
    async def tick(self, now: float) -> int:
        moment = datetime.fromtimestamp(now, UTC)
        count = 0
        for schedule in self.schedules:
            slot = latest_slot(schedule, moment)
            if self.last.get(schedule.name) == slot:
                continue
            first = schedule.name not in self.last
            late = (moment - slot) > schedule.grace
            if first and late and schedule.missed == "skip":
                self.last[schedule.name] = slot
                log.info("schedule_skipped name=%s slot=%s", schedule.name, slot.isoformat())
                continue
            if await self.submit(schedule, slot):
                self.last[schedule.name] = slot
                count += 1
        return count

    # 登记一个时段的任务；排队已满等业务错误只写日志。
    async def submit(self, schedule: Schedule, slot: datetime) -> bool:
        key = f"schedule:{schedule.name}:{slot.isoformat()}"
        try:
            async with self.database.write() as connection:
                await self.queue.submit(
                    connection, schedule.contract, schedule.input, SYSTEM, key=key, request_id=""
                )
        except BusinessError as error:
            log.warning("schedule_submit_failed name=%s code=%s", schedule.name, error.code)
            return False
        return True
