"""
业务现状显式运行观察：只读当前配置数据库，有界编号/状态摘要，不读取业务正文。
"""

import time
from typing import Any

from fastapi_project.development.business_state import database_identity
from sqlalchemy import func, select

from shared.db.database import Database
from shared.jobs.tables import jobs
from shared.modules.catalog import Catalog
from shared.pipelines.tables import runs
from shared.records.tables import run_records


# 数量完整，例子最多十条；省略数量明确，不把列表上限当真实总量。
async def attention(
    connection: Any, table: Any, condition: Any, fields: list[Any]
) -> dict[str, Any]:
    count = int(await connection.scalar(select(func.count()).select_from(table).where(condition)))
    rows = (await connection.execute(select(*fields).where(condition).limit(10))).mappings().all()
    return dict(
        count=count, examples=[dict(row) for row in rows], omitted=max(0, count - len(rows))
    )


# 最近顶层操作只读取编号与状态，不读取包含业务字段的body。
async def recent_operation(connection: Any, name: str) -> Any:
    query = (
        select(
            run_records.c.id, run_records.c.contract, run_records.c.status, run_records.c.started_at
        )
        .where(run_records.c.module == name, run_records.c.parent_id == "")
        .order_by(run_records.c.started_at.desc())
        .limit(1)
    )
    return (await connection.execute(query)).mappings().first()


# 最近运行只列历史事实；当前源码是否成功、真实业务是否验收仍需相应证据。
async def observe(database: Database, catalog: Catalog) -> dict[str, Any]:
    result = {}
    async with database.read() as connection:
        for name, module in catalog.modules.items():
            recent = await recent_operation(connection, name)
            latest = {}
            for pipeline in module.pipelines:
                row = (
                    (
                        await connection.execute(
                            select(runs.c.id, runs.c.state, runs.c.created_at, runs.c.overdue)
                            .where(runs.c.pipeline == pipeline.name)
                            .order_by(runs.c.created_at.desc())
                            .limit(1)
                        )
                    )
                    .mappings()
                    .first()
                )
                latest[pipeline.name] = dict(row) if row else "未知：无持久运行记录"
            overdue = await attention(
                connection,
                runs,
                runs.c.pipeline.in_([p.name for p in module.pipelines])
                & runs.c.overdue
                & runs.c.state.not_in(("succeeded", "skipped")),
                [runs.c.id, runs.c.pipeline, runs.c.state, runs.c.complete_by],
            )
            confirmation = await attention(
                connection,
                jobs,
                jobs.c.contract.in_([op.name for op in module.provides])
                & jobs.c.state.in_(("unknown", "blocked")),
                [jobs.c.id, jobs.c.contract, jobs.c.state],
            )
            result[name] = dict(
                last=dict(
                    operation=dict(recent) if recent else "未知：无持久运行记录",
                    pipelines=latest,
                    evidence="数据库历史观察，不证明当前源码成功或业务验收",
                ),
                overdue=overdue,
                confirmation=confirmation,
                observed_at=time.time(),
                database_id=database_identity(database.url),
            )
    return result
