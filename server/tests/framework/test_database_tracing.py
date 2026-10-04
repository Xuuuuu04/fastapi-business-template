"""
数据库记录验证实际返回值、延迟、失败和只读限制，并检查容量截断不会假装记录完整。
"""

import asyncio
from dataclasses import asdict
from pathlib import Path

import pytest
from sqlalchemy import column, literal, select, table, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from shared.db.access import Db
from shared.db.tracing import MAX_DATABASE_CALLS
from shared.errors.framework import StepRuleBroken
from shared.records.models import StepRecord

pytestmark = pytest.mark.anyio


# 测试通过真实 SQLite 连接读取；只延迟驱动执行，不替换业务返回值。
async def test_query_latency_values_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/queries.db")
    record = StepRecord(
        "s", "load", "读取", "read", "", "service/test_pkg/steps/load.py:1", database_complete=True
    )
    try:
        async with engine.connect() as connection:
            original = type(connection).execute

            # 模拟确实花时间的数据库请求。
            async def delayed(current, statement):
                await asyncio.sleep(0.02)
                return await original(current, statement)

            monkeypatch.setattr(type(connection), "execute", delayed)
            db = Db(connection, read_only=True, place="读取", record=record)
            rows = await db.all(select(literal("private-result").label("value")))
            assert rows[0]["value"] == "private-result"
            assert record.database[0].rows == 1 and record.database[0].elapsed_ms >= 15
            with pytest.raises(OperationalError):
                await db.all(select(column("missing_column")))
            with pytest.raises(StepRuleBroken, match="saves=True"):
                await db.change(update(table("missing_table", column("x"))).values(x=1))
        assert [call.status for call in record.database] == ["ok", "failed", "failed"]
        assert record.database[1].error_code == "OperationalError"
        assert record.database_count == 3 and record.database_elapsed_ms >= 30
        assert "private-result" not in str(asdict(record)) and "missing_column" not in str(
            asdict(record)
        )
    finally:
        await engine.dispose()


# 超出容量的查询继续执行和统计，图不能把被省略的调用假装成没有发生。
async def test_query_detail_limit_is_explicit(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/limit.db")
    record = StepRecord("s", "count", "计数", "read", "", "step.py:1", database_complete=True)
    try:
        async with engine.connect() as connection:
            db = Db(connection, read_only=True, place="计数", record=record)
            for _ in range(MAX_DATABASE_CALLS + 1):
                assert await db.scalar(select(literal(7))) == 7
        assert record.database_count == MAX_DATABASE_CALLS + 1
        assert len(record.database) == MAX_DATABASE_CALLS and not record.database_complete
        assert record.database_elapsed_ms > sum(call.elapsed_ms for call in record.database)
    finally:
        await engine.dispose()
