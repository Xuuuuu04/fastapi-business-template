from dataclasses import replace

import pytest
from sqlalchemy import func, insert, select

from app.setup.build import Services
from shared.errors.framework import InvalidInput
from shared.pipelines.gate import PipelineGate
from shared.pipelines.recovery import resume
from shared.public import All, Data, Flow, Member, Stage, contract, meaning, step
from tests.framework.fanout_sample import Batch, PlanWork, SumWork, Total, module, pipeline
from tests.framework.segment_sample import (
    BatchInput,
    BatchResult,
    BatchStore,
    batch,
    output,
    sample_metadata,
    source,
)
from tests.framework.segment_sample import module as segment_module
from tests.framework.test_fanout import drain, fanout

pytestmark = pytest.mark.anyio
__all__ = ["fanout"]


class Cursor(Data):
    after: int = meaning("上次已提交结束行", default=0)


@step("登记分段成员", reads=["count", "version"], writes=["result"], saves=True)
async def plan_segment(data: PlanWork, pipeline: PipelineGate) -> None:
    await pipeline.add_members([Member[BatchInput](key="batch", input=BatchInput(total=15000))])
    data.result = Batch(count=1)


@step("汇总计算已完成分段成员", reads=["count"], writes=["result"])
async def combine_segment(data: SumWork, pipeline: PipelineGate) -> None:
    page = await pipeline.results("requests", BatchResult)
    data.result = Total(
        count=len(page.items), value=sum(item.result.processed for item in page.items), versions=[1]
    )


async def configure(services: Services):
    from shared.modules.catalog import Catalog

    final = contract(
        "fanout_sample.finish_batch",
        "汇总计算分段成员",
        input=Batch,
        output=Total,
        access="fanout_sample.run",
        effect="command",
    )
    group = replace(pipeline.stages[1], stages=(Stage("batch", batch),), join=All(), max_parallel=1)
    changed = replace(
        pipeline,
        stages=(
            pipeline.stages[0],
            group,
            Stage("combine", final, members={"requests": BatchResult}),
        ),
    )
    provides = dict(module.provides)
    provides[group.operation] = Flow(
        "登记分段成员", work=PlanWork, result="result", steps=[plan_segment]
    )
    provides[final] = Flow(
        "汇总计算分段成员", work=SumWork, result="result", steps=[combine_segment]
    )
    jobs = (*module.jobs, replace(module.jobs[-1], contract=final))
    owner = replace(module, provides=provides, pipelines=(changed,), jobs=jobs)
    segmented = replace(segment_module, jobs=(replace(segment_module.jobs[0], cursor=Cursor),))
    services.catalog = services.queue.catalog = services.runtime.catalog = Catalog(
        [owner, segmented]
    )
    services.queue.pipelines.catalog = services.catalog
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
        await connection.execute(insert(source), [{"id": i} for i in range(1, 15001)])
    return changed, owner, segmented


async def test_segmented_member_keeps_checkpoint(fanout: Services, monkeypatch) -> None:
    from shared.pipelines.plan import StartRequest
    from tests.framework.fanout_sample import Begin
    from tests.framework.test_pipelines import CALLER

    changed, owner, segmented = await configure(fanout)
    original = BatchStore.save

    async def fail(self, start, end):
        count = await original(self, start, end)
        if start == 5000:
            raise ValueError("第二批合成故障")
        return count

    monkeypatch.setattr(BatchStore, "save", fail)
    data = changed.start.input(
        request=StartRequest[Begin](data=Begin(count=1), cycle_key="segment")
    )
    run_id = await fanout.runtime.submit(changed.start, data, caller=CALLER)
    assert (await drain(fanout, run_id))["state"] == "failed"
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 5000
    unsafe = replace(segmented, jobs=(replace(segmented.jobs[0], segmented=False),))
    from shared.pipelines.recovery import validate_checkpoint
    from shared.pipelines.tables import members

    async with fanout.database.write() as connection:
        job_id = await connection.scalar(select(members.c.job_id))
        with pytest.raises(InvalidInput, match="不能改成普通任务"):
            await validate_checkpoint(connection, job_id, unsafe.jobs[0], "batch")
    monkeypatch.setattr(BatchStore, "save", original)
    await resume(fanout.database, fanout.catalog, run_id)
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(output)) == 15000
        assert await connection.scalar(select(func.sum(output.c.value))) == 15000 * 15001
