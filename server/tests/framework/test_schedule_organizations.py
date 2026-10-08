"""
多组织定时：按组织去重、旧单组织周期不重复、失败隔离和实际时段输入。
所有操作使用独立测试模块，不预置任何业务组织。
"""

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
from shared.modules.catalog import Catalog
from shared.public import Data, meaning
from tests.framework.sample_modules import SlowInput, calc_module, slow

pytestmark = pytest.mark.anyio


# 同计划两组织各登记一份，多进程反复触发也不重复。
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


# 模块声明可选择组织，明确空元组表示全局，不被部署的组织列表复制执行。
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


# 旧单组织已经提交本周期时复用原任务，不改变已有任务或重新触发。
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


# 周期元组没有分隔符碰撞，组织长编号也不超过数据库键长度。
def test_period_key_is_unambiguous_and_bounded() -> None:
    slot = datetime(2026, 10, 8, tzinfo=UTC)
    assert period_key("x:a", "b", slot) != period_key("x", "a:b", slot)
    assert len(period_key("name" * 20, "a" * 64, slot)) <= 120


# 配置有重复、通配或旧新范围矛盾时启动前拒绝。
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


# 周期字段是嵌套输入的一部分，构建时不修改声明过的静态输入。
class Window(Data):
    end: datetime = meaning("本次计划时段")


# 仅用于证明多层字段替换，替换后的时段随任务输入保存。
class WindowInput(Data):
    request: Window = meaning("窗口")


# 使用新的不可变模型，延迟和重试不重新计算时段。
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


# 计划时间、组织、周期字段和任务参数都参与目录摘要。
def test_job_and_schedule_configuration_changes_digest() -> None:
    from shared.modules.digest import digest_of

    baseline = digest_of([calc_module])
    changed = replace(
        calc_module, jobs=tuple(replace(plan, lease_seconds=99) for plan in calc_module.jobs)
    )
    assert digest_of([changed]) != baseline
    timer = Schedule("minute", "每分钟", slow, SlowInput(mark="t"), every=timedelta(minutes=1))
    first = replace(calc_module, schedules=(timer,))
    second = replace(first, schedules=(replace(timer, org_ids=("alpha",)),))
    assert digest_of([first]) != digest_of([second])
    assert Catalog([first]).digest == digest_of([first])
