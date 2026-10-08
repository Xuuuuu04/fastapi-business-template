"""
后台任务和定时计划的声明写法，写在模块的 module.py 中。
JobPlan 说明哪个操作可以作为后台任务运行、失败后怎样重试、执行期限过期后能否安全重复；
Schedule 说明按什么时间自动登记这个任务。领取、重试和状态维护由框架负责。
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Literal

from shared.data.models import Data
from shared.modules.contract import Contract


# 后台任务的自动重试次数和每次等待时间。
@dataclass(frozen=True)
class Retry:
    times: int = 0
    waits: tuple[float, ...] = (10.0, 60.0, 300.0)

    # 返回第几次失败后需要等待的秒数。
    def wait_after(self, attempt: int) -> float:
        if not self.waits:
            return 0.0
        return self.waits[min(attempt, len(self.waits)) - 1]


# 一个操作的后台执行要求，包括重试、重复执行安全性和排队上限。
@dataclass(frozen=True, eq=False)
class JobPlan:
    contract: Contract[Any, Any]
    retry: Retry = field(default_factory=Retry)
    repeat_safe: bool = False
    max_queued: int = 1000
    lease_seconds: float = 60.0
    segmented: bool = False
    cursor: type[Data] | None = None


# 一个定时任务的输入与触发时间，交给调度进程登记执行。
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


# 把本次实际计划时段写入明确字段，重试继续使用同一份冻结输入。
def build_slot_input(schedule: Schedule, slot: datetime) -> Data:
    if not schedule.slot_input_field:
        return schedule.input
    values = schedule.input.model_dump()
    target = values
    parts = schedule.slot_input_field.split(".")
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            raise ValueError("定时输入字段的父对象不存在")
        target = nested
    if parts[-1] not in target:
        raise ValueError("定时输入字段不存在")
    target[parts[-1]] = slot
    return schedule.contract.input.model_validate(values)
