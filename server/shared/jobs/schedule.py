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


class Scheduler:
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

    async def tick(self, now: float) -> int:
        moment = datetime.fromtimestamp(now, UTC)
        count = 0
        for schedule in self.schedules:
            targets = self.org_ids if schedule.org_ids is None else schedule.org_ids
            for org_id in targets or ("*",):
                if await self.tick_org(schedule, moment, org_id):
                    count += 1
        return count

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
