from pathlib import Path

import pytest

from app.setup.build import build
from shared.access.caller import SYSTEM
from shared.public import Data, Flow, Module, WorkData, contract, meaning, step
from shared.scenarios.observations import (
    ExpectedObservation,
    ObservationJournal,
    ObservationPoint,
    ObservationPosition,
    capture,
)
from tests.testing_app import make_settings


class Input(Data):
    amount: int = meaning("合成数量")


class Output(Data):
    total: int = meaning("合成结果")


class Work(WorkData):
    amount: int = meaning("合成数量")
    partial: int = meaning("中间数量")
    result: Output = meaning("最终结果")


@step("计算中间数量", reads=["amount"], writes=["partial"], observes=["partial"])
def calculate(data: Work) -> None:
    data.partial = data.amount * 2


@step("整理结果", reads=["partial"], writes=["result"], observes=["result"])
def produce(data: Work) -> None:
    data.result = Output(total=data.partial + 1)


operation = contract(
    "sample_counts.run", "合成计算", input=Input, output=Output, access="public", effect="query"
)
module = Module(
    "sample_counts",
    "合成计算",
    "1",
    {operation: Flow("计算", work=Work, result="result", steps=[calculate, produce])},
    kind="capability",
)


@pytest.mark.anyio
async def test_observed_order_and_positions(tmp_path: Path) -> None:
    services = build(make_settings(tmp_path), modules=[module])
    journal = ObservationJournal()
    position = ObservationPosition(batch=3, member="item-a", attempt=2)
    try:
        with capture(journal, position):
            result = await services.runtime.run(operation, Input(amount=4), caller=SYSTEM)
        assert result.total == 9 and len(journal.items) == 2
        first = ObservationPoint(operation.name, "calculate", "partial", 3, "item-a", 2)
        second = ObservationPoint(operation.name, "produce", "result", 3, "item-a", 2)
        missing = ObservationPoint(operation.name, "unrecorded", "other", 3, "item-a", 2)
        differences = journal.compare(
            [
                ExpectedObservation(second, {"total": 11}),
                ExpectedObservation(first, 7),
                ExpectedObservation(missing, 1),
            ]
        )
        assert differences[0].point == first and differences[0].sequence == 1
        message = str(differences[0])
        assert "第 1 步 sample_counts.run.calculate" in message
        assert "字段 partial：实际 8，期望 7" in message
        assert "test_observation_points.py:" in message
        assert differences[-1].point == missing and differences[-1].status == "unknown"
        assert not journal.compare(
            [ExpectedObservation(first, 8), ExpectedObservation(second, {"total": 9})]
        )
        assert "value" not in str(journal.summary())
    finally:
        await services.close()


def test_snapshot_and_safe_summary() -> None:
    journal = ObservationJournal()
    point = ObservationPoint("sample_counts.run", "calculate", "partial")
    value = {"private": ["synthetic-private-value"]}
    journal.record(point, value)
    value["private"].append("changed")
    assert journal.items[0].value == {"private": ["synthetic-private-value"]}
    assert "synthetic-private-value" not in repr(journal.items)
    assert "synthetic-private-value" not in str(journal.summary())


def test_difference_values_are_bounded_and_not_in_summary() -> None:
    journal = ObservationJournal()
    point = ObservationPoint("sample_counts.run", "calculate", "partial")
    journal.record(point, "x" * 2000, source="service/sample_counts/steps/build.py:12")
    difference = journal.compare([ExpectedObservation(point, "y" * 2000)])[0]
    assert len(str(difference)) < 500
    assert "build.py:12" in str(difference)
    assert "x" * 100 not in repr(difference)
    assert "x" * 100 not in str(journal.summary())


def test_ambiguous_observation_is_not_a_pass() -> None:
    journal = ObservationJournal()
    point = ObservationPoint("sample_counts.run", "calculate", "partial")
    journal.record(point, 8)
    journal.record(point, 8)
    assert journal.compare([ExpectedObservation(point, 8)])[0].status == "ambiguous"
