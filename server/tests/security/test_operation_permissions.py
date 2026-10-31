from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.setup.build import Services
from shared.access.caller import Caller
from shared.errors.framework import NotAllowed
from shared.jobs.tables import jobs
from tests.framework.sample_modules import CalcInput, calc, outer
from tests.framework.test_runner import count_notes

pytestmark = pytest.mark.anyio


async def test_nested_operation_requires_its_own_permission(sample: Services) -> None:
    caller = Caller("tester", "user", "测试用户", frozenset({outer.access}), "test")
    with pytest.raises(NotAllowed, match=calc.access):
        await sample.runtime.run(outer, CalcInput(amount=Decimal("1")), caller=caller)
    assert await count_notes(sample) == 0


async def test_nested_operation_with_explicit_permissions(sample: Services) -> None:
    caller = Caller("tester", "user", "测试用户", frozenset({outer.access, calc.access}), "test")
    result = await sample.runtime.run(outer, CalcInput(amount=Decimal("1")), caller=caller)
    assert result.saved == 2


async def test_queue_refuses_before_creating_job(sample: Services) -> None:
    caller = Caller("tester", "user", "测试用户", frozenset(), "test")
    with pytest.raises(NotAllowed):
        await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=caller)
    async with sample.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(jobs)) == 0
