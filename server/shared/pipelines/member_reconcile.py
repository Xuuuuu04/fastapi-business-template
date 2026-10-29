from typing import TYPE_CHECKING

from sqlalchemy import select

from shared.pipelines.member_pool import advance
from shared.pipelines.plan import FanOut
from shared.pipelines.storage import root_for
from shared.pipelines.tables import runs, stages

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue


async def reconcile(queue: "JobQueue") -> None:
    if not queue.catalog.pipelines:
        return
    async with queue.database.read() as connection:
        ids = (
            (
                await connection.execute(
                    select(runs.c.id)
                    .where(runs.c.state == "waiting_members")
                    .order_by(runs.c.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
    for run_id in ids:
        async with queue.database.write() as connection:
            root = await root_for(connection, run_id)
            if root["state"] != "waiting_members":
                continue
            pipeline = queue.catalog.pipelines.get(root["pipeline"])
            group = (
                next(
                    (stage for stage in pipeline.stages if stage.name == root["current_stage"]),
                    None,
                )
                if pipeline
                else None
            )
            if not isinstance(group, FanOut):
                continue
            row = dict(
                (
                    await connection.execute(
                        select(stages).where(
                            stages.c.pipeline_id == run_id, stages.c.name == group.name
                        )
                    )
                )
                .mappings()
                .one()
            )
            await advance(connection, queue, root, row, group)
