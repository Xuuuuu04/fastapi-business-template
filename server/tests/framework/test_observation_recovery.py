from dataclasses import replace

import pytest
from sqlalchemy import func, select

from shared.public import Flow
from shared.scenarios.observations import (
    ExpectedObservation,
    ObservationJournal,
    ObservationPoint,
    capture,
)
from tests.framework import fanout_driver, test_segmented_jobs
from tests.framework.fanout_driver import drain, fanout, start
from tests.framework.fanout_sample import Store, collected
from tests.framework.test_provider_effects import Input, service_at
from tests.framework.test_segmented_jobs import execute, segmented, submit

__all__ = ["fanout", "segmented"]
pytestmark = pytest.mark.anyio


def observed(module):
    return replace(
        module,
        provides={
            operation: Flow(
                flow.title,
                work=flow.work,
                result=flow.result,
                steps=[replace(part, observes=part.writes) for part in flow.steps],
            )
            for operation, flow in module.provides.items()
        },
    )


@pytest.fixture(autouse=True)
def capture_modules(monkeypatch):
    monkeypatch.setattr(fanout_driver, "module", observed(fanout_driver.module))
    monkeypatch.setattr(test_segmented_jobs, "module", observed(test_segmented_jobs.module))


async def test_member_retry_has_real_positions(fanout, monkeypatch) -> None:
    from shared.pipelines.recovery import resume

    original = Store.collect

    async def fail(self, id, version):
        value = await original(self, id, version)
        if id == 2:
            raise ValueError("合成成员故障")
        return value

    monkeypatch.setattr(Store, "collect", fail)
    journal = ObservationJournal()
    with capture(journal):
        run_id = await start(fanout, 4)
        assert (await drain(fanout, run_id))["state"] == "failed"
        async with fanout.database.read() as connection:
            assert await connection.scalar(select(func.count()).select_from(collected)) == 3
        monkeypatch.setattr(Store, "collect", original)
        await resume(fanout.database, fanout.catalog, run_id)
        assert (await drain(fanout, run_id))["state"] == "succeeded"
    entries = [item for item in journal.items if item.point.member == "0002"]
    assert entries and all(item.point.attempt is not None for item in entries)
    assert any(item.point.attempt == 2 for item in entries)
    assert [item.sequence for item in journal.items] == list(range(1, len(journal.items) + 1))
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(collected)) == 4


async def test_segment_positions_follow_actual_checkpoint(segmented) -> None:
    job = await submit(segmented, total=6, batch_size=2)
    journal = ObservationJournal()
    with capture(journal):
        await execute(segmented)
    result_points = [item for item in journal.items if item.point.field == "result"]
    assert [item.point.batch for item in result_points] == [1, 2, 3]
    assert [item.value["processed"] for item in result_points] == [2, 4, 6]
    assert all(item.point.attempt == 1 for item in result_points)
    assert all(item.point.operation == "segment_sample.process" for item in result_points)
    await test_segmented_jobs.assert_complete(segmented, job, 6)


async def test_effect_count_and_restart_are_independent_expectations(tmp_path) -> None:
    from shared.access.caller import SYSTEM
    from shared.effects.service import EffectService

    service, spec, adapter, database = await service_at(tmp_path)
    try:
        reply = await service.call(spec, Input(message="synthetic"), SYSTEM, "once", [], [])
        restarted = EffectService(service.store, {spec: adapter})
        repeated = await restarted.call(spec, Input(message="synthetic"), SYSTEM, "once", [], [])
        assert reply == repeated and adapter.sent == 1
        journal = ObservationJournal()
        point = ObservationPoint("sample_messages.send", "external_receipt", "state")
        journal.record(point, reply.state)
        assert not journal.compare([ExpectedObservation(point, "accepted")])
        assert journal.compare([ExpectedObservation(point, "completed")])[0].status == "mismatch"
    finally:
        await database.close()
