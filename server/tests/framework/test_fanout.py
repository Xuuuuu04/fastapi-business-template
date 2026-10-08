"""
200成员完整链验收，证明队列有界、固定来源及成功成员结果不重复不遗漏。
"""

import time
from pathlib import Path

import pytest
from sqlalchemy import func, insert, select

from app.setup.build import Services, build
from shared.jobs.tables import job_counts, jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.pipelines.plan import StartRequest
from shared.pipelines.tables import members, runs, stages
from tests.framework.fanout_sample import (
    Begin,
    collected,
    module,
    pipeline,
    sample_metadata,
    versions,
)
from tests.framework.test_pipelines import CALLER
from tests.testing_app import make_settings, prepare_test_database

pytestmark = pytest.mark.anyio


# 所有成员样例共用独立夹具，不增加业务模块；双库运行同一套用例。
@pytest.fixture
async def fanout(tmp_path: Path):
    settings = make_settings(tmp_path)
    await prepare_test_database(settings.database_url)
    built = build(settings, modules=[module])
    async with built.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
        await connection.execute(insert(versions).values(version=1))
    try:
        yield built
    finally:
        async with built.database.write() as connection:
            await connection.run_sync(sample_metadata.drop_all)
        await built.close()


# 通过公开流程入口登记，成员数量只作为有界初始Data。
async def start(services: Services, count: int = 200) -> str:
    data = pipeline.start.input(
        request=StartRequest[Begin](data=Begin(count=count), cycle_key="members")
    )
    return await services.runtime.submit(pipeline.start, data, caller=CALLER)


# 用实际worker逐个领取，定时检查成员池，记录真实峰值而非预设并发数。
async def drain(services: Services, run_id: str, *, limit: int = 2000) -> dict:
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    peak = 0
    for _ in range(limit):
        await services.queue.pipelines.reconcile()
        async with services.database.read() as connection:
            active = await connection.scalar(
                select(func.count())
                .select_from(members.join(jobs, members.c.job_id == jobs.c.id))
                .where(jobs.c.state.in_(("queued", "running", "waiting_retry")))
            )
            peak = max(peak, int(active or 0))
            counts = (await connection.execute(select(job_counts.c.active))).scalars().all()
            assert all(count <= 3 for count in counts)
            root = (
                (await connection.execute(select(runs).where(runs.c.id == run_id))).mappings().one()
            )
            if root["state"] in ("succeeded", "failed", "unknown", "version_blocked"):
                return dict(root, peak=peak)
        ticket = await services.queue.claim(time.time() + 0.05)
        if ticket is None:
            raise AssertionError("活动流程没有可推进成员或明确等待任务")
        await worker.execute(ticket)
    raise AssertionError("成员链没有在声明阶段数内结束")


# 第一阶段后插入新的上游版本，200个成员仍全部消费旧的固定来源。
async def test_200_members_wait_join_and_frozen_sources(fanout: Services) -> None:
    run_id = await start(fanout)
    ticket = await fanout.queue.claim(time.time())
    assert ticket is not None
    await Worker(fanout.runtime, fanout.queue, [], WorkerOptions()).execute(ticket)
    async with fanout.database.write() as connection:
        await connection.execute(insert(versions).values(version=2))
    root = await drain(fanout, run_id)
    assert root["state"] == "succeeded" and 0 < root["peak"] <= 8
    async with fanout.database.read() as connection:
        rows = (await connection.execute(select(collected))).mappings().all()
        assert len(rows) == 200 and {row["id"] for row in rows} == set(range(1, 201))
        assert {row["version"] for row in rows} == {1}
        assert (
            await connection.scalar(
                select(func.count()).select_from(members).where(members.c.accepted.is_(True))
            )
            == 200
        )
        result = await connection.scalar(
            select(stages.c.output_json).where(
                stages.c.pipeline_id == run_id, stages.c.name == "combine"
            )
        )
    assert result == '{"count":200,"value":20100,"versions":[1]}'


# 成功成员保留真实主键与运行号，修好一个成员后只补这个成员当前阶段。
async def test_retry_only_failed_member(fanout: Services, monkeypatch) -> None:
    from shared.pipelines.recovery import resume
    from tests.framework.fanout_sample import Store

    original = Store.collect

    # 成员5在SQL写入后出错，事务必须撤销它。
    async def fail(self, id, version):
        result = await original(self, id, version)
        if id == 5:
            raise ValueError("成员5合成故障")
        return result

    monkeypatch.setattr(Store, "collect", fail)
    run_id = await start(fanout, 20)
    root = await drain(fanout, run_id)
    assert root["state"] == "failed"
    async with fanout.database.read() as connection:
        successful = (
            await connection.execute(
                select(members.c.key, members.c.run_id).where(members.c.state == "succeeded")
            )
        ).all()
        assert len(successful) == 19
        assert await connection.scalar(select(func.count()).select_from(collected)) == 19
    monkeypatch.setattr(Store, "collect", original)
    await resume(fanout.database, fanout.catalog, run_id)
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        saved = (
            await connection.execute(
                select(members.c.key, members.c.run_id).where(members.c.key != "0005")
            )
        ).all()
        assert dict(saved) == dict(successful)
        assert await connection.scalar(select(func.count()).select_from(collected)) == 20


# Ratio只纳入达到比例时的结果，剩余成员不会偷偷混进本次汇算。
async def test_ratio_seals_accepted_results(fanout: Services) -> None:
    from dataclasses import replace

    from shared.modules.catalog import Catalog
    from shared.public import Ratio

    group = replace(pipeline.stages[1], join=Ratio(0.5, required=("0001",)))
    changed = replace(pipeline, stages=(pipeline.stages[0], group, pipeline.stages[2]))
    fanout.catalog = fanout.queue.catalog = fanout.runtime.catalog = Catalog(
        [replace(module, pipelines=(changed,))]
    )
    fanout.queue.pipelines.catalog = fanout.catalog
    data = changed.start.input(request=StartRequest[Begin](data=Begin(count=20), cycle_key="ratio"))
    run_id = await fanout.runtime.submit(changed.start, data, caller=CALLER)
    root = await drain(fanout, run_id)
    assert root["state"] == "succeeded"
    async with fanout.database.read() as connection:
        accepted = (
            (await connection.execute(select(members.c.key).where(members.c.accepted.is_(True))))
            .scalars()
            .all()
        )
        assert len(accepted) == 10 and "0001" in accepted
        result = await connection.scalar(
            select(stages.c.output_json).where(stages.c.name == "combine")
        )
    import json

    total = json.loads(result)
    assert total["count"] == 10
    assert total["value"] == sum(int(key) for key in accepted)


# 未知外部效果始终停下，即使Ratio本来可能达标也不自动推进。
async def test_unknown_member_requires_separate_confirmation(fanout: Services, monkeypatch) -> None:
    from shared.errors.framework import InvalidInput, RemoteResultUnknown
    from shared.pipelines.recovery import resume
    from tests.framework.fanout_sample import Store

    original = Store.collect

    # 只模拟结果未知，不发送真实请求。
    async def unknown(self, id, version):
        if id == 2:
            raise RemoteResultUnknown("成员2结果未知")
        return await original(self, id, version)

    monkeypatch.setattr(Store, "collect", unknown)
    run_id = await start(fanout, 8)
    assert (await drain(fanout, run_id))["state"] == "unknown"
    with pytest.raises(InvalidInput, match="待确认"):
        await resume(fanout.database, fanout.catalog, run_id)
    worker = Worker(fanout.runtime, fanout.queue, [], WorkerOptions())
    # 把暂停后仍排队的动作领取为暂停状态，不继续访问上游。
    for _ in range(20):
        ticket = await fanout.queue.claim(time.time() + 1)
        if ticket is None:
            break
        await worker.execute(ticket)
    monkeypatch.setattr(Store, "collect", original)
    await resume(fanout.database, fanout.catalog, run_id, confirm_unknown=True)
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(collected)) == 8


# 同周期按组织各自登记，成员结果和来源状态互不覆盖。
async def test_members_are_organization_scoped(fanout: Services) -> None:
    from dataclasses import replace

    first = await start(fanout, 6)
    data = pipeline.start.input(
        request=StartRequest[Begin](data=Begin(count=6), cycle_key="members")
    )
    other = await fanout.runtime.submit(
        pipeline.start, data, caller=replace(CALLER, org_id="org-b")
    )
    assert first != other
    assert (await drain(fanout, first))["state"] == "succeeded"
    assert (await drain(fanout, other))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        rows = (
            await connection.execute(
                select(collected.c.org_id, func.count()).group_by(collected.c.org_id)
            )
        ).all()
    assert dict(rows) == {"org-a": 6, "org-b": 6}


# 子阶段声明变化暂停，内部模块版本变化继续，并保留前面的实际结果。
async def test_member_version_pause_and_resume(fanout: Services) -> None:
    from dataclasses import replace

    from shared.modules.catalog import Catalog
    from shared.pipelines.recovery import resume

    run_id = await start(fanout, 6)
    worker = Worker(fanout.runtime, fanout.queue, [], WorkerOptions())
    for _ in range(2):
        ticket = await fanout.queue.claim(time.time())
        assert ticket is not None
        await worker.execute(ticket)
    group = pipeline.stages[1]
    changed_group = replace(group, stages=(group.stages[0], replace(group.stages[1], every=0.002)))
    changed = replace(pipeline, stages=(pipeline.stages[0], changed_group, pipeline.stages[2]))
    fanout.catalog = fanout.queue.catalog = fanout.runtime.catalog = Catalog(
        [replace(module, version="2", pipelines=(changed,))]
    )
    fanout.queue.pipelines.catalog = fanout.catalog
    assert (await drain(fanout, run_id))["state"] == "version_blocked"
    # 领取暂停的排队任务，使它们释放队列名额。
    for _ in range(10):
        ticket = await fanout.queue.claim(time.time() + 1)
        if ticket is None:
            break
        await worker.execute(ticket)
    await resume(fanout.database, fanout.catalog, run_id, accept_schema=True)
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert set((await connection.execute(select(members.c.module_version))).scalars()) == {"2"}
