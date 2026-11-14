import secrets

from sqlalchemy import Column, Float, Index, String, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.db.database import Database
from shared.db.tables import metadata
from shared.timing.current import now as business_now

audit_records = Table(
    "system_audit_records",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("actor", String(120), nullable=False),
    Column("org_id", String(64), nullable=False),
    Column("contract", String(120), nullable=False),
    Column("status", String(20), nullable=False),
    Column("request_id", String(64), nullable=False),
    Column("run_id", String(32), nullable=False),
    Column("created_at", Float, nullable=False),
    Index("ix_system_audit_created", "created_at"),
    Index("ix_system_audit_org", "org_id", "created_at"),
)


async def record(
    connection: AsyncConnection,
    caller: Caller,
    contract: str,
    status: str,
    request_id: str = "",
    run_id: str = "",
) -> None:
    await connection.execute(
        insert(audit_records).values(
            id=secrets.token_hex(16),
            actor=f"{caller.kind}:{caller.id}",
            org_id=caller.org_id,
            contract=contract,
            status=status,
            request_id=request_id,
            run_id=run_id,
            created_at=business_now(),
        )
    )


async def record_after(
    database: Database,
    caller: Caller,
    contract: str,
    status: str,
    request_id: str = "",
    run_id: str = "",
) -> None:
    async with database.write() as connection:
        await record(connection, caller, contract, status, request_id, run_id)


async def recent(database: Database, limit: int, org_id: str = "") -> list[dict[str, object]]:
    query = select(audit_records).order_by(audit_records.c.created_at.desc()).limit(limit)
    if org_id:
        query = query.where(audit_records.c.org_id == org_id)
    async with database.read() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [dict(row) for row in rows]
