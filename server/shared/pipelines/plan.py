from dataclasses import dataclass, field
from datetime import datetime, time
from functools import cached_property
from typing import Any, Literal, cast

from shared.data.fields import meaning
from shared.data.models import Data, WorkData
from shared.modules.contract import Contract, contract


class StartRequest[Input: Data](Data):
    data: Input = meaning("流程初始数据")
    cycle_key: str = meaning("明确周期键；留空时使用period", default="")
    period: datetime | None = meaning("定时计划的实际时段", default=None, empty="人工指定周期键")


class StartInput[Input: Data](Data):
    request: StartRequest[Input] = meaning("流程周期与初始数据")


class PipelineView(Data):
    id: str = meaning("流程运行编号")
    state: str = meaning("流程状态")
    reused: bool = meaning("是否复用同一周期", default=False)


class StartWork[Input: Data](WorkData):
    request: StartRequest[Input] = meaning("流程周期与初始数据")
    result: PipelineView = meaning("流程运行")


@dataclass(frozen=True)
class Stage:
    name: str
    operation: Contract[Any, Any]
    input_from: str = "previous"
    freeze_sources: bool = field(default=False, kw_only=True)
    source: type[Data] | None = field(default=None, kw_only=True)
    members: dict[str, type[Data]] = field(default_factory=dict, kw_only=True)


@dataclass(frozen=True)
class Wait(Stage):
    ready_field: str = "ready"
    every: float = 30.0
    timeout: float = 3600.0
    max_parallel: int = 1


@dataclass(frozen=True)
class DailyTime:
    at: time
    zone: str = "Asia/Shanghai"
    days_after: int = 0


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

    @cached_property
    def start(self) -> Contract[Any, PipelineView]:
        module, action = self.name.split(".", 1)
        return contract(
            f"{module}.start_{action}",
            f"启动{self.title}",
            input=cast(Any, StartInput)[self.input],
            output=PipelineView,
            access=self.access or f"{module}.run",
            effect="command",
        )


@dataclass(frozen=True)
class All:
    pass


@dataclass(frozen=True)
class Ratio:
    success: float
    required: tuple[str, ...] = ()


@dataclass(frozen=True)
class FanOut(Stage):
    stages: tuple[Stage, ...] = ()
    join: All | Ratio = field(default_factory=All)
    max_parallel: int = 8


class Member[Input: Data](Data):
    key: str = meaning("流程阶段内唯一成员键", min_length=1, max_length=120)
    input: Input = meaning("成员初始数据")


class MemberResult[Output: Data](Data):
    key: str = meaning("稳定成员键")
    result: Output = meaning("已确认产出")


class MemberPage[Output: Data](Data):
    items: list[MemberResult[Output]] = meaning("本页已纳入汇合的结果")
    next_after: str = meaning("下一页游标；空表示结束", default="")


def stages_of(pipeline: Pipeline) -> tuple[Stage, ...]:
    return tuple(
        stage
        for parent in pipeline.stages
        for stage in (parent, *(parent.stages if isinstance(parent, FanOut) else ()))
    )
