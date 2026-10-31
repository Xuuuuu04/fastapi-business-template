from dataclasses import dataclass, field
from datetime import datetime, time
from functools import cached_property
from typing import Any, Literal, cast

from shared.data.fields import meaning
from shared.data.models import Data, WorkData
from shared.modules.contract import Contract, contract


class StartRequest[Input: Data](Data):
    data: Input = meaning("流程初始数据")
    cycle_key: str = meaning("本次业务周期的唯一标识；留空时根据 period 生成", default="")
    period: datetime | None = meaning(
        "本次流程所属周期的时间，定时启动时由计划提供",
        default=None,
        empty="已用 cycle_key 指定本次周期",
    )


class StartInput[Input: Data](Data):
    request: StartRequest[Input] = meaning("本次流程的周期标识和初始输入")


class PipelineView(Data):
    id: str = meaning("流程运行编号")
    state: str = meaning("流程状态")
    reused: bool = meaning("是否返回同一周期已有的流程", default=False)


class StartWork[Input: Data](WorkData):
    request: StartRequest[Input] = meaning("本次流程的周期标识和初始输入")
    result: PipelineView = meaning("流程编号和当前状态")


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
    key: str = meaning("子任务的唯一标识，同一并行阶段内不能重复", min_length=1, max_length=120)
    input: Input = meaning("子任务的初始输入")


class MemberResult[Output: Data](Data):
    key: str = meaning("子任务的唯一标识，重试时保持不变")
    result: Output = meaning("子任务已完成并保存的结果")


class MemberPage[Output: Data](Data):
    items: list[MemberResult[Output]] = meaning("本页用于汇总的子任务结果")
    next_after: str = meaning("下一页的起始位置；空字符串表示没有下一页", default="")


def stages_of(pipeline: Pipeline) -> tuple[Stage, ...]:
    return tuple(
        stage
        for parent in pipeline.stages
        for stage in (parent, *(parent.stages if isinstance(parent, FanOut) else ()))
    )
