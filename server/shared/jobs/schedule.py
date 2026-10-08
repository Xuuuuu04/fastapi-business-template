"""
定时计划：计算每个计划最近一个到期的时段，并以“计划名称加时段”作为请求编号登记任务。
多个 worker 同时计算也只会登记一次；错过的时段按声明跳过（skip）或只补最近一次（latest）。
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from shared.db.database import Database
from shared.errors.kinds import BusinessError
from shared.jobs.organizations import configured_orgs, legacy_exists, period_key, schedule_caller
from shared.jobs.plan import Schedule, build_slot_input
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
        raise ValueError(f"定时计划“{schedule.title}”需要设置 every 或 daily_at")
    today = datetime.combine(local.date(), schedule.daily_at, tzinfo=zone)
    return today if today <= local else today - timedelta(days=1)


# 根据模块登记的定时计划生成任务，避免同一时间重复登记。
class Scheduler:
    # 记住每个计划上一次处理的时段，避免同一进程反复登记。
    def __init__(
        self,
        schedules: list[Schedule],
        queue: JobQueue,
        database: Database,
        org_id: str = "",
        org_ids: tuple[str, ...] = (),
    ) -> None:
        self.org_ids = configured_orgs(org_id, org_ids)
        self.schedules = schedules
        self.queue = queue
        self.database = database
        self.last: dict[tuple[str, str], datetime] = {}

    # 检查全部计划，为新到期的时段登记任务；返回本次登记的数量。
    async def tick(self, now: float) -> int:
        moment = datetime.fromtimestamp(now, UTC)
        count = 0
        for schedule in self.schedules:
            targets = self.org_ids if schedule.org_ids is None else schedule.org_ids
            for org_id in targets or ("*",):
                if await self.tick_org(schedule, moment, org_id):
                    count += 1
        return count

    # 一个组织失败不影响其他组织，已登记的时段不反复提交。
    async def tick_org(self, schedule: Schedule, moment: datetime, org_id: str) -> bool:
        slot, identity = latest_slot(schedule, moment), (schedule.name, org_id)
        if self.last.get(identity) == slot:
            return False
        if (
            identity not in self.last
            and moment - slot > schedule.grace
            and schedule.missed == "skip"
        ):
            self.last[identity] = slot
            log.info(
                "schedule_skipped name=%s org=%s slot=%s", schedule.name, org_id, slot.isoformat()
            )
            return False
        if await self.submit(schedule, slot, org_id):
            self.last[identity] = slot
            return True
        return False

    # 登记一个时段的任务；排队已满等业务错误只写日志。
    async def submit(self, schedule: Schedule, slot: datetime, org_id: str = "*") -> bool:
        key = period_key(schedule.name, org_id, slot)
        try:
            async with self.database.write() as connection:
                if org_id != "*" and await legacy_exists(
                    connection, schedule.name, schedule.contract.name, org_id, slot
                ):
                    return True
                await self.queue.submit(
                    connection,
                    schedule.contract,
                    build_slot_input(schedule, slot),
                    schedule_caller(org_id),
                    key=key,
                    request_id="",
                )
        except BusinessError as error:
            log.warning(
                "schedule_submit_failed name=%s org=%s code=%s", schedule.name, org_id, error.code
            )
            return False
        return True
