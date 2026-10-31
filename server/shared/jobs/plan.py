import hashlib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Literal

from shared.data.models import Data
from shared.jobs.imports import ImportPlan
from shared.jobs.limits import ResourceLimit, SerialKey
from shared.modules.contract import Contract


@dataclass(frozen=True)
class Retry:
    times: int = 0
    waits: tuple[float, ...] = (10.0, 60.0, 300.0)

    def wait_after(self, attempt: int) -> float:
        if not self.waits:
            return 0.0
        return self.waits[min(attempt, len(self.waits)) - 1]


@dataclass(frozen=True, eq=False)
class JobPlan:
    contract: Contract[Any, Any]
    retry: Retry = field(default_factory=Retry)
    repeat_safe: bool = False
    max_queued: int = 1000
    lease_seconds: float = 60.0
    segmented: bool = False
    cursor: type[Data] | None = None
    import_plan: ImportPlan | None = None
    serial: SerialKey | None = None
    resources: tuple[ResourceLimit, ...] = ()
    queue_timeout: float | None = None
    valid_until_field: str = ""
    revalidate: Contract[Any, Any] | None = None
    attempt_timeout: float | None = None

    def submission(self, input: Data, key: str) -> tuple[str, str, str]:
        body = input.model_dump_json()
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return body, digest, self.import_plan.queue_key() if self.import_plan else key


@dataclass(frozen=True, eq=False)
class Schedule:
    name: str
    title: str
    contract: Contract[Any, Any]
    input: Data
    every: timedelta | None = None
    daily_at: time | None = None
    zone: str = "Asia/Shanghai"
    missed: Literal["skip", "latest"] = "skip"
    grace: timedelta = timedelta(minutes=10)
    org_ids: tuple[str, ...] | None = None
    slot_input_field: str = ""


def build_slot_input(schedule: Schedule, slot: datetime) -> Data:
    if not schedule.slot_input_field:
        return schedule.input
    values = schedule.input.model_dump()
    target = values
    parts = schedule.slot_input_field.split(".")
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            raise ValueError("定时执行的输入中不存在此字段的父对象")
        target = nested
    if parts[-1] not in target:
        raise ValueError("定时执行的输入中不存在此字段")
    target[parts[-1]] = slot
    return schedule.contract.input.model_validate(values)
