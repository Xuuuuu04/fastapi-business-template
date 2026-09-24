"""
模块声明 Module：一个业务模块对外说明自己的全部内容，写在模块的 module.py 中。
provides 把操作约定对应到实现它的流程；store 给出数据访问的实现；
tables、remotes、prompts、jobs、schedules 分别登记本模块的表、外部系统、提示词、后台任务和定时计划；
publishes、subscribes 登记本模块发布的事件和订阅的事件（见 shared/events）。
全局只在 app/setup/catalog.py 中列出启用哪些模块，不再重复登记这些内容。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Table

from shared.events.event import Event, Subscription
from shared.flow.flow import Flow
from shared.jobs.plan import JobPlan, Schedule
from shared.model_calls.prompt import Prompt
from shared.modules.contract import Contract
from shared.remote_calls.remote import Remote

STORE_PARAMS = ("db", "legacy", "remote", "files", "cache", "caller")


@dataclass(frozen=True, eq=False)
class Module:
    name: str
    title: str
    version: str
    provides: Mapping[Contract[Any, Any], Flow]
    store: Callable[..., object] | None = None
    tables: tuple[Table, ...] = ()
    remotes: tuple[Remote, ...] = ()
    prompts: tuple[Prompt, ...] = ()
    jobs: tuple[JobPlan, ...] = ()
    schedules: tuple[Schedule, ...] = ()
    publishes: tuple[Event, ...] = ()
    subscribes: tuple[Subscription, ...] = ()

    # 模块的业务文档目录，位于项目根目录的 doc/ 下。
    @property
    def doc(self) -> str:
        return f"doc/{self.name}"
