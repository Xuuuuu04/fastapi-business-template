"""
模块事件的声明：发布方在自己的 public.py 中用 event() 声明“发生了什么”，订阅方在 module.py 中
用 on() 声明“发生后由哪个操作处理”。发布方不知道有哪些订阅方，模块之间不因此产生调用依赖。
事件与发布它的业务写入在同一事务中登记到任务表，订阅方由 worker 异步执行，自带重试和幂等。
"""

from dataclasses import dataclass, field
from typing import Any

from shared.data.models import Data
from shared.jobs.plan import JobPlan, Retry
from shared.modules.contract import Contract


@dataclass(frozen=True, eq=False)
class Event:
    name: str
    title: str
    data: type[Data]

    # 事件名的前缀是发布它的模块名。
    @property
    def module(self) -> str:
        return self.name.split(".", 1)[0]


@dataclass(frozen=True, eq=False)
class Subscription:
    event: Event
    handler: Contract[Any, Any]
    retry: Retry = field(default_factory=lambda: Retry(times=3))
    max_queued: int = 10000

    # 订阅方处理事件时按后台任务执行；同一事件在同一运行中只登记一次，重复执行是安全的。
    def plan(self) -> JobPlan:
        return JobPlan(self.handler, retry=self.retry, repeat_safe=True, max_queued=self.max_queued)


# 声明一个事件：名称写成“模块名.事件名”，data 是事件携带的数据类型。
def event(name: str, title: str, *, data: type[Data]) -> Event:
    return Event(name, title, data)


# 声明订阅：事件发生后，由本模块的 handler 操作处理，输入就是事件数据。
def on(
    item: Event,
    handler: Contract[Any, Any],
    *,
    retry: Retry | None = None,
    max_queued: int = 10000,
) -> Subscription:
    return Subscription(item, handler, retry or Retry(times=3), max_queued)
