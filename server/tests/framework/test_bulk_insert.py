"""
批插必须保留逐行默认值、范围和只读检查，且实际只执行一条 INSERT。
"""

from itertools import count

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, event, func, select
from sqlalchemy.ext.asyncio import create_async_engine

from shared.access.caller import Caller
from shared.db.access import Db
from shared.db.org import org_column
from shared.db.owner import owner_column
from shared.errors.framework import StepRuleBroken
from shared.records.models import StepRecord
from tests.testing_app import database_url


# 检查末行权限、只读及规模拒绝，核对实际SQL与逐行默认值。
@pytest.mark.anyio
async def test_bulk_defaults_scope_and_statement_count(tmp_path) -> None:
    metadata = MetaData()
    sequence = count(1)
    probe = Table(
        "strict_bulk_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        org_column(),
        owner_column("probe.manage"),
        Column("sequence", Integer, default=lambda: next(sequence)),
    )
    engine = create_async_engine(database_url(tmp_path))
    inserts = []

    # 记录真实驱动发出的批插语句次数。
    def observe(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO strict_bulk_probe"):
            inserts.append(1)

    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    caller = Caller("u1", "user", "合成用户", frozenset(), "north")
    rows = [dict(id=i, org_id="north", owner_id="u1") for i in range(100)]
    part = StepRecord("s", "save", "批插", "save", "", "test_bulk_insert.py")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            db = Db(connection, read_only=False, place="批插", caller=caller, record=part)
            for key, value in [("org_id", "south"), ("owner_id", "u2")]:
                bad = [dict(row) for row in rows]
                bad[-1][key] = value
                with pytest.raises(StepRuleBroken):
                    await db.insert_many(probe, bad)
            with pytest.raises(StepRuleBroken, match="saves=True"):
                await Db(connection, read_only=True, place="读取", caller=caller).insert_many(
                    probe, rows
                )
            with pytest.raises(StepRuleBroken, match="100行"):
                await db.insert_many(probe, rows + [dict(id=100, org_id="north", owner_id="u1")])
            assert await db.insert_many(probe, []) == 0
            assert await db.insert_many(probe, rows) == 100
            assert inserts == [1]
            assert part.database[-1].rows == 100
            assert await connection.scalar(select(func.count()).select_from(probe)) == 100
            defaults = (await connection.execute(select(probe.c.sequence))).scalars().all()
            assert sorted(defaults) == list(range(1, 101))
            await connection.run_sync(metadata.drop_all)
    finally:
        await engine.dispose()
