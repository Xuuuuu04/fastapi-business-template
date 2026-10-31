from decimal import Decimal
from typing import Any

import pytest

from shared.data.fields import meaning
from shared.data.models import WorkData
from shared.errors.framework import StepRuleBroken
from shared.flow.view import FieldTypes, StepView


class LimitedWork(WorkData):
    count: int = meaning("数量", gt=0, le=10)
    title: str = meaning("名称", min_length=1, max_length=3)
    amount: Decimal = meaning("金额", max_digits=5, decimal_places=2)
    items: list[int] = meaning("项目", min_length=1, max_length=2)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count", 0),
        ("count", 11),
        ("count", "1"),
        ("title", ""),
        ("title", "过长的名称"),
        ("amount", Decimal("1.001")),
        ("amount", Decimal("1000")),
        ("items", []),
        ("items", [1, 2, 3]),
    ],
)
def test_step_rejects_field_limits(field: str, value: Any) -> None:
    values: dict[str, Any] = {}
    view = StepView(values, (), (field,), FieldTypes(LimitedWork), "写入样例")
    with pytest.raises(StepRuleBroken, match=field):
        setattr(view, field, value)
    assert values == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count", 1),
        ("count", 10),
        ("title", "名"),
        ("title", "三个字"),
        ("amount", Decimal("999.99")),
        ("items", [1, 2]),
    ],
)
def test_step_accepts_field_boundaries(field: str, value: Any) -> None:
    values: dict[str, Any] = {}
    view = StepView(values, (), (field,), FieldTypes(LimitedWork), "写入样例")
    setattr(view, field, value)
    assert values == {field: value}
