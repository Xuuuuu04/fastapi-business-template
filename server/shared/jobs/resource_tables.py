"""
资源额度与执行位置由数据库跨worker共享，位置有尝试编号和租期，等待不保留事务。
"""

from sqlalchemy import Column, Float, Integer, String, Table

from shared.db.tables import metadata

pools = Table(
    "system_resource_pools",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("cooldown_until", Float, nullable=False),
    Column("next_position", Integer, nullable=False, default=0),
)

leases = Table(
    "system_resource_leases",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("pool_id", String(64), nullable=False, index=True),
    Column("owner", String(64), nullable=False, index=True),
    Column("attempt", Integer, nullable=False),
    Column("lease_until", Float, nullable=False),
    Column("cooldown", Float, nullable=False),
)
