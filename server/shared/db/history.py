"""
数据变更历史：谁在什么时候、通过哪次运行，把哪张表哪条记录的哪个字段从什么值改成了什么值。
由 Db.update_tracked 在同一事务中写入，业务回滚时历史也一起撤销；不随运行记录清理。
标记为 secret 的列（例如密码摘要）只记“已修改”，不保存前后的值。
"""

import secrets
import time
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Column, Float, Index, String, Table, Text, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.db.database import Database
from shared.db.tables import metadata
from shared.db.tracing import query_record
from shared.records.models import StepRecord

HIDDEN = "（已隐藏）"
MAX_VALUE = 1000

change_history = Table(
    "system_change_history",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("table_name", String(80), nullable=False),
    Column("record_key", String(80), nullable=False),
    Column("field", String(80), nullable=False),
    Column("before", Text, nullable=False),
    Column("after", Text, nullable=False),
    Column("actor", String(120), nullable=False),
    Column("org_id", String(64), nullable=False),
    Column("run_id", String(32), nullable=False),
    Column("created_at", Float, nullable=False),
    Index("ix_system_change_record", "table_name", "record_key", "created_at"),
    Index("ix_system_change_org", "org_id", "created_at"),
)


# 列出一批记录修改前后不同的字段，写成历史行。
def history_rows(
    table: Table,
    key: str,
    before: Sequence[Mapping[Any, Any]],
    values: Mapping[str, Any],
    caller: Caller,
    run_id: str,
) -> list[dict[str, Any]]:
    now = time.time()
    rows = []
    for old in before:
        for field, new in values.items():
            if old[field] == new:
                continue
            secret = bool(table.c[field].info.get("secret"))
            rows.append(
                {
                    "id": secrets.token_hex(16),
                    "table_name": table.name,
                    "record_key": str(old[key]),
                    "field": field,
                    "before": HIDDEN if secret else text_of(old[field]),
                    "after": HIDDEN if secret else text_of(new),
                    "actor": f"{caller.kind}:{caller.id}",
                    "org_id": caller.org_id,
                    "run_id": run_id,
                    "created_at": now,
                }
            )
    return rows


# 值的文字形式；空值写成空文字，过长的截断。
def text_of(value: Any) -> str:
    return "" if value is None else str(value)[:MAX_VALUE]


# 在给定事务中写入历史行。
async def save_history(
    connection: AsyncConnection,
    rows: list[dict[str, Any]],
    record: StepRecord | None = None,
    target: str = "database",
) -> None:
    if rows:
        statement = insert(change_history)
        with query_record(record, statement, "history", target) as call:
            await connection.execute(statement, rows)
            if call is not None:
                call.rows = len(rows)


# 查询变更历史；org_id 为空表示全部组织，table 和 key 为空表示不筛选。
async def recent_changes(
    database: Database, limit: int, org_id: str = "", table: str = "", key: str = ""
) -> list[dict[str, object]]:
    query = select(change_history).order_by(change_history.c.created_at.desc()).limit(limit)
    if org_id:
        query = query.where(change_history.c.org_id == org_id)
    if table:
        query = query.where(change_history.c.table_name == table)
    if key:
        query = query.where(change_history.c.record_key == key)
    async with database.read() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [dict(row) for row in rows]
