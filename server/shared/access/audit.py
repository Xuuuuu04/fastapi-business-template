"""
审计记录保存到独立表，不随诊断记录清理。成功的业务操作与业务写入同一事务提交。
拒绝和失败的操作在回滚后单独写入，避免失败事务撤销审计。
"""

import secrets
import time

from sqlalchemy import Column, Float, Index, String, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.db.database import Database
from shared.db.tables import metadata

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


# 在给定事务中写入一条不包含业务正文和密钥的审计记录。
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
            created_at=time.time(),
        )
    )


# 失败或权限拒绝后，使用独立事务保存审计记录。
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


# 查询最近的审计记录；只返回元数据，不读取业务输入或输出。
async def recent(database: Database, limit: int, org_id: str = "") -> list[dict[str, object]]:
    query = select(audit_records).order_by(audit_records.c.created_at.desc()).limit(limit)
    if org_id:
        query = query.where(audit_records.c.org_id == org_id)
    async with database.read() as connection:
        rows = (await connection.execute(query)).mappings().all()
    return [dict(row) for row in rows]
