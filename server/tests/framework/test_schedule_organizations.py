import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.setup.build import Services
from shared.access.caller import SYSTEM
from shared.config.settings import Settings
from shared.jobs.organizations import period_key, schedule_caller
from shared.jobs.plan import Schedule, build_slot_input
from shared.jobs.schedule import Scheduler, latest_slot
from shared.jobs.tables import jobs
from shared.public import Data, meaning
from tests.framework.sample_modules import SlowInput, slow

pytestmark = pytest.mark.anyio


async def test_schedule_runs_once_per_org(sample: Services) -> None:
    timer = Schedule("minute", "每分钟", slow, SlowInput(mark="t"), every=timedelta(minutes=1))
    first = Scheduler([timer], sample.queue, sample.database, org_ids=("alpha", "beta"))
    second = Scheduler([timer], sample.queue, sample.database, org_ids=("alpha", "beta"))
    now = datetime(2026, 10, 8, 0, 0, tzinfo=UTC).timestamp()
    assert await first.tick(now) == 2
    assert await first.tick(now) == 0
    await second.tick(now)
    async with sample.database.read() as connection:
        rows = (await connection.execute(select(jobs))).mappings().all()
    assert len(rows) == 2 and len({row["key"] for row in rows}) == 2
    assert {json.loads(row["caller_json"])["org_id"] for row in rows} == {"alpha", "beta"}
    assert {json.loads(row["caller_json"])["id"] for row in rows} == {SYSTEM.id}


async def test_module_org_selection_and_global_task(sample: Services) -> None:
    timer = Schedule(
        "minute", "每分钟", slow, SlowInput(mark="t"), every=timedelta(minutes=1), org_ids=("beta",)
    )
    now = datetime(2026, 10, 8, 0, 0, tzinfo=UTC).timestamp()
    scheduler = Scheduler([timer], sample.queue, sample.database, org_ids=("alpha", "beta"))
    assert await scheduler.tick(now) == 1
    global_timer = replace(timer, name="global", org_ids=())
    assert (
        await Scheduler(
            [global_timer], sample.queue, sample.database, org_ids=("alpha", "beta")
        ).tick(now)
        == 1
    )
    async with sample.database.read() as connection:
        rows = (await connection.execute(select(jobs.c.caller_json))).scalars().all()
    assert {json.loads(row)["org_id"] for row in rows} == {"beta", "*"}


async def test_existing_single_org_slot_is_reused(sample: Services) -> None:
    timer = Schedule("minute", "每分钟", slow, SlowInput(mark="t"), every=timedelta(minutes=1))
    now = datetime(2026, 10, 8, 0, 0, tzinfo=UTC)
    slot = latest_slot(timer, now)
    async with sample.database.write() as connection:
        await sample.queue.submit(
            connection,
            slow,
            timer.input,
            schedule_caller("alpha"),
            key=f"schedule:minute:{slot.isoformat()}",
            request_id="",
        )
    scheduler = Scheduler([timer], sample.queue, sample.database, org_id="alpha")
    assert await scheduler.tick(now.timestamp()) == 1
    async with sample.database.read() as connection:
        rows = (await connection.execute(select(jobs))).all()
    assert len(rows) == 1


def test_period_key_is_unambiguous_and_bounded() -> None:
    slot = datetime(2026, 10, 8, tzinfo=UTC)
    assert period_key("x:a", "b", slot) != period_key("x", "a:b", slot)
    assert len(period_key("name" * 20, "a" * 64, slot)) <= 120


@pytest.mark.parametrize(
    "values",
    [
        {"schedule_org_ids": ["a", "a"]},
        {"schedule_org_ids": ["*"]},
        {"schedule_org_ids": [""]},
        {"schedule_org_id": "a", "schedule_org_ids": ["b"]},
    ],
)
def test_invalid_org_configuration_is_rejected(values) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


class Window(Data):
    end: datetime = meaning("本次计划时段")


class WindowInput(Data):
    request: Window = meaning("窗口")


def test_slot_input_preserves_original() -> None:
    from shared.public import contract

    operation = contract(
        "sample_window.run", "窗口", input=WindowInput, output=WindowInput, access="public"
    )
    old = WindowInput(request=Window(end=datetime(2026, 10, 1, tzinfo=UTC)))
    timer = Schedule(
        "window", "窗口", operation, old, every=timedelta(hours=1), slot_input_field="request.end"
    )
    current = datetime(2026, 10, 8, tzinfo=UTC)
    replaced = build_slot_input(timer, current)
    assert replaced.request.end == current and old.request.end.day == 1
