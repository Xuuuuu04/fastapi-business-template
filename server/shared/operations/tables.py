"""
跨worker共享容量暂停事实；通知复用已有system_notifications。
"""

from sqlalchemy import Boolean, Column, Float, String, Table, Text

from shared.db.tables import metadata

state = Table(
    "system_ops_state",
    metadata,
    Column("name", String(40), primary_key=True),
    Column("paused", Boolean, nullable=False),
    Column("observed_at", Float, nullable=False),
    Column("body", Text, nullable=False),
)
