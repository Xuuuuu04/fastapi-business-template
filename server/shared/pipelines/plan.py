"""
多阶段流程声明：每个阶段引用已登记的公开后台操作，输入只来自初始Data或已成功阶段。
"""

from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from typing import Any, Literal, cast

from shared.data.fields import meaning
from shared.data.models import Data, WorkData
from shared.modules.contract import Contract, contract


# 一次流程的周期和类型明确的初始数据。
class StartRequest[Input: Data](Data):
    data: Input = meaning("流程初始数据")
    cycle_key: str = meaning("明确周期键；留空时使用period", default="")
    period: datetime | None = meaning("定时计划的实际时段", default=None, empty="人工指定周期键")


# 流程启动入口的输入。
class StartInput[Input: Data](Data):
    request: StartRequest[Input] = meaning("流程周期与初始数据")


# 流程启动或重复触发返回的同一运行。
class PipelineView(Data):
    id: str = meaning("流程运行编号")
    state: str = meaning("流程状态")
    reused: bool = meaning("是否复用同一周期", default=False)


# 框架启动操作的内部数据，不进入产品业务目录。
class StartWork[Input: Data](WorkData):
    request: StartRequest[Input] = meaning("流程周期与初始数据")
    result: PipelineView = meaning("流程运行")


# 一个阶段的公开操作和输入来源；previous表示上一阶段，首阶段表示初始输入。
@dataclass(frozen=True)
class Stage:
    name: str
    operation: Contract[Any, Any]
    input_from: str = "previous"


# 等待阶段每次只检查一次，最多并行执行max_parallel次检查。
@dataclass(frozen=True)
class Wait(Stage):
    ready_field: str = "ready"
    every: float = 30.0
    timeout: float = 3600.0
    max_parallel: int = 1


# 一个模块声明的流程，默认跳过仍与上一周期重叠的新周期。
@dataclass(frozen=True)
class Pipeline:
    name: str
    title: str
    input: type[Data]
    stages: tuple[Stage, ...]
    overlap: Literal["skip", "queue"] = "skip"
    access: str = ""

    # 自动登记的公开启动操作，可被Schedule引用。
    @cached_property
    def start(self) -> Contract[Any, PipelineView]:
        module, action = self.name.split(".", 1)
        return contract(
            f"{module}.start_{action}",
            f"启动{self.title}",
            input=cast(Any, StartInput)[self.input],
            output=PipelineView,
            access=self.access or f"{module}.run",
        )
