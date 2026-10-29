from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic_core import to_jsonable_python


@dataclass(frozen=True)
class ObservationPoint:
    operation: str
    step: str
    field: str
    batch: int | None = None
    member: str = ""
    attempt: int | None = None


@dataclass(frozen=True)
class ObservationPosition:
    batch: int | None = None
    member: str = ""
    attempt: int | None = None


@dataclass(frozen=True)
class Observation:
    point: ObservationPoint
    sequence: int
    value: Any = field(repr=False)
    observed: bool = True
    source: str = ""


@dataclass(frozen=True)
class ExpectedObservation:
    point: ObservationPoint
    value: Any = field(repr=False)


@dataclass(frozen=True)
class ObservationDifference:
    point: ObservationPoint
    sequence: int | None
    status: str
    actual: Any = field(default=None, repr=False)
    expected: Any = field(default=None, repr=False)
    source: str = ""

    def __str__(self) -> str:
        def bounded(value: Any) -> str:
            text = repr(value)
            return text if len(text) <= 160 else text[:157] + "..."

        return (
            f"第 {self.sequence or '?'} 步 {self.point.operation}.{self.point.step}"
            f"（{self.source or '位置未知'}）字段 {self.point.field}："
            f"实际 {bounded(self.actual)}，期望 {bounded(self.expected)}（{self.status}）"
        )


class ObservationJournal:
    def __init__(self) -> None:
        self.items: list[Observation] = []

    def record(
        self, point: ObservationPoint, value: Any, *, observed: bool = True, source: str = ""
    ) -> None:
        self.items.append(
            Observation(point, len(self.items) + 1, to_jsonable_python(value), observed, source)
        )

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

    def summary(self) -> list[dict[str, Any]]:
        return [
            dict(point=asdict(item.point), sequence=item.sequence, observed=item.observed)
            for item in self.items
        ]


CURRENT: ContextVar[ObservationJournal | None] = ContextVar("scenario_observations", default=None)
POSITION: ContextVar[ObservationPosition | None] = ContextVar("scenario_position", default=None)


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
