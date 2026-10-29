import pytest
from sqlalchemy import func, insert, select

from app.setup.build import Services
from shared.jobs.worker import Worker, WorkerOptions
from shared.pipelines.plan import StartRequest
from shared.pipelines.tables import members, stages
from tests.framework.fanout_driver import drain, fanout, now, start
from tests.framework.fanout_sample import (
    Begin,
    collected,
    module,
    pipeline,
    versions,
)
from tests.framework.test_pipelines import CALLER

pytestmark = pytest.mark.anyio
__all__ = ["fanout", "drain", "start"]


async def test_200_members_wait_join_and_frozen_sources(fanout: Services) -> None:
    run_id = await start(fanout)
    ticket = await fanout.queue.claim(now())
    assert ticket is not None
    await Worker(fanout.runtime, fanout.queue, [], WorkerOptions()).execute(ticket)
    async with fanout.database.write() as connection:
        await connection.execute(insert(versions).values(version=2))
    root = await drain(fanout, run_id)
    assert root["state"] == "succeeded" and 0 < root["peak"] <= 8, (
        root["state"],
        root["peak"],
        root["reason"],
    )
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


async def test_retry_only_failed_member(fanout: Services, monkeypatch) -> None:
    from shared.pipelines.recovery import resume
    from tests.framework.fanout_sample import Store

    original = Store.collect

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


async def test_unknown_member_requires_separate_confirmation(fanout: Services, monkeypatch) -> None:
    from shared.errors.framework import InvalidInput, RemoteResultUnknown
    from shared.pipelines.recovery import resume
    from tests.framework.fanout_sample import Store

    original = Store.collect

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
    for _ in range(20):
        ticket = await fanout.queue.claim(now() + 1)
        if ticket is None:
            break
        await worker.execute(ticket)
    monkeypatch.setattr(Store, "collect", original)
    await resume(fanout.database, fanout.catalog, run_id, confirm_unknown=True)
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(collected)) == 8


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


async def test_member_version_pause_and_resume(fanout: Services) -> None:
    from dataclasses import replace

    from shared.modules.catalog import Catalog
    from shared.pipelines.recovery import resume

    run_id = await start(fanout, 6)
    worker = Worker(fanout.runtime, fanout.queue, [], WorkerOptions())
    for _ in range(2):
        ticket = await fanout.queue.claim(now())
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
    for _ in range(10):
        ticket = await fanout.queue.claim(now() + 1)
        if ticket is None:
            break
        await worker.execute(ticket)
    await resume(fanout.database, fanout.catalog, run_id, accept_schema=True)
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert set((await connection.execute(select(members.c.module_version))).scalars()) == {"2"}
