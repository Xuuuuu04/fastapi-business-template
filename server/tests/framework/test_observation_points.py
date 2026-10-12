"""
实际执行器观察步骤与位置，按真实顺序报告首个差异，不记录的位置保留未知。
"""

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


# 明确类型输入与输出，不从实现生成样例预期。
class Input(Data):
    amount: int = meaning("合成数量")


# 合成结果供真实流程完成。
class Output(Data):
    total: int = meaning("合成结果")


# 中间数量与结果分别在各步骤产生。
class Work(WorkData):
    amount: int = meaning("合成数量")
    partial: int = meaning("中间数量")
    result: Output = meaning("最终结果")


# 算中间值，观察点由步骤明确声明。
@step("计算中间数量", reads=["amount"], writes=["partial"], observes=["partial"])
def calculate(data: Work) -> None:
    data.partial = data.amount * 2


# 最终结果与中间观察分开，不把正确结果推定为每一步都正确。
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


# 预期列表故意反向，首个差异仍由真实执行顺序决定。
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
        assert differences[-1].point == missing and differences[-1].status == "unknown"
        assert not journal.compare(
            [ExpectedObservation(first, 8), ExpectedObservation(second, {"total": 9})]
        )
        assert "value" not in str(journal.summary())
    finally:
        await services.close()


# 普通请求不主动捕获原文；已记录值是快照，不会随之后的对象变化而变化。
def test_snapshot_and_safe_summary() -> None:
    journal = ObservationJournal()
    point = ObservationPoint("sample_counts.run", "calculate", "partial")
    value = {"private": ["synthetic-private-value"]}
    journal.record(point, value)
    value["private"].append("changed")
    assert journal.items[0].value == {"private": ["synthetic-private-value"]}
    assert "synthetic-private-value" not in repr(journal.items)
    assert "synthetic-private-value" not in str(journal.summary())


# 同一位置重复而没有成员或尝试区分时，不能悄悄取最后一次作为成功。
def test_ambiguous_observation_is_not_a_pass() -> None:
    journal = ObservationJournal()
    point = ObservationPoint("sample_counts.run", "calculate", "partial")
    journal.record(point, 8)
    journal.record(point, 8)
    assert journal.compare([ExpectedObservation(point, 8)])[0].status == "ambiguous"
