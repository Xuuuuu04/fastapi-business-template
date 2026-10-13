"""
样例主动启用的内存观察账本；实际顺序统一编号，原始取值不进入普通运行记录。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic_core import to_jsonable_python


# 同名字段通过操作、步骤、批次、成员与尝试位置区分，避免把几次执行拼成一次。
@dataclass(frozen=True)
class ObservationPoint:
    operation: str
    step: str
    field: str
    batch: int | None = None
    member: str = ""
    attempt: int | None = None


# 调度位置由执行入口传递，不能从同名字段或观察值猜批次和成员。
@dataclass(frozen=True)
class ObservationPosition:
    batch: int | None = None
    member: str = ""
    attempt: int | None = None


# 原值仅在样例比较内存中使用，repr和公共摘要不会自动展开它。
@dataclass(frozen=True)
class Observation:
    point: ObservationPoint
    sequence: int
    value: Any = field(repr=False)
    observed: bool = True
    source: str = ""


# 独立的期望来自确认样例，不从运行记录生成或反推。
@dataclass(frozen=True)
class ExpectedObservation:
    point: ObservationPoint
    value: Any = field(repr=False)


# 定位只显示地址和原因，详细值由显式私有样例资料管理。
@dataclass(frozen=True)
class ObservationDifference:
    point: ObservationPoint
    sequence: int | None
    status: str
    actual: Any = field(default=None, repr=False)
    expected: Any = field(default=None, repr=False)
    source: str = ""

    # 仅测试账本的显式失败消息展示有界取值，公共摘要仍然不含值。
    def __str__(self) -> str:
        def bounded(value: Any) -> str:
            text = repr(value)
            return text if len(text) <= 160 else text[:157] + "..."

        return (
            f"第 {self.sequence or '?'} 步 {self.point.operation}.{self.point.step}"
            f"（{self.source or '位置未知'}）字段 {self.point.field}："
            f"实际 {bounded(self.actual)}，期望 {bounded(self.expected)}（{self.status}）"
        )


# 只在明确的样例范围启用，正式请求没有账本时不会记录取值。
class ObservationJournal:
    # 每轮保留真实观察顺序，比较结果不改变已观察事实。
    def __init__(self) -> None:
        self.items: list[Observation] = []

    # 序列化成快照，后续步骤修改对象不会改写过去观察。
    def record(
        self, point: ObservationPoint, value: Any, *, observed: bool = True, source: str = ""
    ) -> None:
        self.items.append(
            Observation(point, len(self.items) + 1, to_jsonable_python(value), observed, source)
        )

    # 先按实际执行顺序寻找差异，未记录的位置最后作为未知报告。
    def compare(self, expected: list[ExpectedObservation]) -> list[ObservationDifference]:
        values = {item.point: item.value for item in expected}
        if len(values) != len(expected):
            raise ValueError("样例重复声明同一观察位置，请明确批次、成员和尝试")
        seen: set[ObservationPoint] = set()
        differences = []
        for item in self.items:
            if item.point not in values:
                continue
            if item.point in seen:
                differences.append(
                    ObservationDifference(
                        item.point,
                        item.sequence,
                        "ambiguous",
                        item.value,
                        values[item.point],
                        item.source,
                    )
                )
            elif not item.observed:
                differences.append(
                    ObservationDifference(
                        item.point,
                        item.sequence,
                        "unknown",
                        None,
                        values[item.point],
                        item.source,
                    )
                )
            elif item.value != to_jsonable_python(values[item.point]):
                differences.append(
                    ObservationDifference(
                        item.point,
                        item.sequence,
                        "mismatch",
                        item.value,
                        values[item.point],
                        item.source,
                    )
                )
            seen.add(item.point)
        differences += [
            ObservationDifference(item.point, None, "unknown", expected=item.value)
            for item in expected
            if item.point not in seen
        ]
        return differences

    # 只保存观察地址和状态，不让业务原文随检查历史被复制。
    def summary(self) -> list[dict[str, Any]]:
        return [
            dict(point=asdict(item.point), sequence=item.sequence, observed=item.observed)
            for item in self.items
        ]


CURRENT: ContextVar[ObservationJournal | None] = ContextVar("scenario_observations", default=None)
POSITION: ContextVar[ObservationPosition | None] = ContextVar("scenario_position", default=None)


# 并发测试或请求各自继承自己的观察范围，退出和取消都会恢复原范围。
@contextmanager
def capture(
    journal: ObservationJournal, position: ObservationPosition | None = None
) -> Iterator[ObservationJournal]:
    token = CURRENT.set(journal)
    place = POSITION.set(position)
    try:
        yield journal
    finally:
        CURRENT.reset(token)
        POSITION.reset(place)
