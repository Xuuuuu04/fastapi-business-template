"""
多阶段流程声明：每个阶段引用已登记的公开后台操作，输入只来自初始Data或已成功阶段。
"""

from dataclasses import dataclass, field
from datetime import datetime, time
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
    freeze_sources: bool = field(default=False, kw_only=True)
    source: type[Data] | None = field(default=None, kw_only=True)
    members: dict[str, type[Data]] = field(default_factory=dict, kw_only=True)


# 等待阶段每次只检查一次，最多并行执行max_parallel次检查。
@dataclass(frozen=True)
class Wait(Stage):
    ready_field: str = "ready"
    every: float = 30.0
    timeout: float = 3600.0
    max_parallel: int = 1


# 按周期所在日的当地时间声明最晚完成点，跨日流程显式设置days_after。
@dataclass(frozen=True)
class DailyTime:
    at: time
    zone: str = "Asia/Shanghai"
    days_after: int = 0


# 一个模块声明的流程，默认跳过仍与上一周期重叠的新周期。
@dataclass(frozen=True)
class Pipeline:
    name: str
    title: str
    input: type[Data]
    stages: tuple[Stage, ...]
    overlap: Literal["skip", "queue"] = "skip"
    access: str = ""
    complete_by: DailyTime | None = None
    on_overdue: Literal["continue", "pause"] = "continue"

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


# 全部成员成功后汇合。
@dataclass(frozen=True)
class All:
    pass


# 达到成功比例，且必需成员成功后汇合。
@dataclass(frozen=True)
class Ratio:
    success: float
    required: tuple[str, ...] = ()


# 规划操作登记成员，每个成员按同一组公开阶段执行，完成后才推进外层流程。
@dataclass(frozen=True)
class FanOut(Stage):
    stages: tuple[Stage, ...] = ()
    join: All | Ratio = field(default_factory=All)
    max_parallel: int = 8


# 一个稳定成员键及其声明过的初始Data，规划步骤可以按批登记。
class Member[Input: Data](Data):
    key: str = meaning("流程阶段内唯一成员键", min_length=1, max_length=120)
    input: Input = meaning("成员初始数据")


# 已纳入本次汇合的成员产出，始终保留稳定成员键。
class MemberResult[Output: Data](Data):
    key: str = meaning("稳定成员键")
    result: Output = meaning("已确认产出")


# 有界成员结果页，大结果继续按引用或游标读取。
class MemberPage[Output: Data](Data):
    items: list[MemberResult[Output]] = meaning("本页已纳入汇合的结果")
    next_after: str = meaning("下一页游标；空表示结束", default="")


# 登记、依赖图和摘要使用同一份公开阶段集合，包含扇出内部阶段。
def stages_of(pipeline: Pipeline) -> tuple[Stage, ...]:
    return tuple(
        stage
        for parent in pipeline.stages
        for stage in (parent, *(parent.stages if isinstance(parent, FanOut) else ()))
    )
