import secrets
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.errors.framework import DuplicateRequest, StepRuleBroken
from shared.flow.view import FieldTypes
from tests.framework.sample_modules import CalcInput, calc
from tests.framework.test_field_limits import LimitedWork


@settings(max_examples=40, derandomize=True)
@given(st.integers(min_value=-1000, max_value=1000))
def test_count_constraint_holds_for_generated_values(value: int) -> None:
    types = FieldTypes(LimitedWork)
    if 1 <= value <= 10:
        assert types.check("count", value, "数量") == value
    else:
        with pytest.raises(StepRuleBroken):
            types.check("count", value, "数量")


@pytest.mark.anyio
@settings(
    max_examples=8,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(st.integers(min_value=0, max_value=100000), st.integers(min_value=1, max_value=4))
async def test_repeated_submission_keeps_one_job(
    sample: Services, cents: int, repeats: int
) -> None:
    key = "property-" + secrets.token_hex(8)
    body = CalcInput(amount=Decimal(cents) / 100)
    first = await sample.runtime.submit(calc, body, caller=DEVELOPER, key=key)
    for _ in range(repeats):
        assert await sample.runtime.submit(calc, body, caller=DEVELOPER, key=key) == first
    with pytest.raises(DuplicateRequest):
        await sample.runtime.submit(
            calc, CalcInput(amount=body.amount + Decimal("0.01")), caller=DEVELOPER, key=key
        )
