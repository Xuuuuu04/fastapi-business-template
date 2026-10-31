import json
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import InvalidInput
from shared.pipelines.schema import declarations
from shared.pipelines.storage import root_for
from shared.pipelines.tables import runs
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.db.database import Database
    from shared.modules.catalog import Catalog


async def resume_queued(
    connection: AsyncConnection,
    database: "Database",
    catalog: "Catalog",
    run_id: str,
    accept_schema: bool,
) -> str:
    from shared.jobs.queue import JobQueue

    root = await root_for(connection, run_id)
    pipeline = catalog.pipelines.get(root["pipeline"])
    if root["state"] != "version_blocked" or pipeline is None or not accept_schema:
        raise InvalidInput("流程尚未登记第一阶段；恢复时必须已登记此流程，并明确接受当前格式")
    queue = JobQueue(catalog, database)
    other = await queue.pipelines.active(connection, root["pipeline"], root["org_id"])
    if other != run_id:
        raise InvalidInput("另一个周期正在运行，不能恢复当前周期")
    pipeline.input.model_validate_json(root["input_json"])
    await connection.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .values(
            declarations_json=json.dumps(declarations(pipeline, catalog)), updated_at=business_now()
        )
    )
    await queue.pipelines.activate(connection, root, pipeline)
    return "已按当前格式登记第一阶段"
