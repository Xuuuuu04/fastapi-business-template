"""
后台任务和定时计划的声明写法，写在模块的 module.py 中。
JobPlan 说明哪个操作可以作为后台任务运行、失败后怎样重试、执行期限过期后能否安全重复；
Schedule 说明按什么时间自动登记这个任务。领取、重试和状态维护由框架负责。
"""

from dataclasses import dataclass, field
from datetime import time, timedelta
from typing import Any, Literal

from shared.data.models import Data
from shared.modules.contract import Contract


@dataclass(frozen=True)
class Retry:
    times: int = 0
    waits: tuple[float, ...] = (10.0, 60.0, 300.0)

    # 返回第几次失败后需要等待的秒数。
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
