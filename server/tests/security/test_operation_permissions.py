from decimal import Decimal

import pytest
from fastapi import Request
from sqlalchemy import func, select
from starlette.types import Scope

from app.api.system.jobs import job as fetch_job
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


def fake_request(services: Services) -> Request:
    app = type("App", (), {"state": type("S", (), {"services": services})()})()
    scope: Scope = {"type": "http", "app": app}
    return Request(scope)


async def test_job_view_checks_anonymous_org_and_kind(sample: Services) -> None:
    owner = Caller("u1", "user", "用户一", frozenset({calc.access}), "org-a")
    anon = Caller("anonymous", "anonymous", "匿名", frozenset({calc.access}), "org-a")
    request = fake_request(sample)
    anon_job = await sample.runtime.submit(calc, CalcInput(amount=Decimal("1")), caller=anon)
    with pytest.raises(NotAllowed):
        await fetch_job(anon_job, request, anon)

    owned_job = await sample.runtime.submit(calc, CalcInput(amount=Decimal("2")), caller=owner)
    assert (await fetch_job(owned_job, request, owner))["id"] == owned_job
    other_org = Caller("u1", "user", "同号异组织", frozenset(), "org-b")
    other_kind = Caller("u1", "service", "同号异类型", frozenset(), "org-a")
    for outsider in (other_org, other_kind):
        with pytest.raises(NotAllowed):
            await fetch_job(owned_job, request, outsider)
