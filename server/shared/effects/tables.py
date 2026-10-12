"""
外部效果意图与逐次尝试证据；业务正文加密保存，迁移和启动不发送任何历史请求。
"""

from sqlalchemy import Boolean, CheckConstraint, Column, Float, Integer, String, Table, Text

from shared.db.tables import metadata

intents = Table(
    "system_effect_intents",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("provider", String(160), nullable=False),
    Column("owner", String(64), nullable=False),
    Column("protocol", String(64), nullable=False),
    Column("binding", String(64), nullable=False),
    Column("input_digest", String(64), nullable=False),
    Column("request", Text, nullable=False),
    Column("state", String(16), nullable=False),
    Column("receipt", Text, nullable=False, default=""),
    Column("external_id", String(200), nullable=False, default=""),
    Column("simulated", Boolean, nullable=False),
    Column("attempt", Integer, nullable=False, default=0),
    Column("lease_until", Float, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    CheckConstraint(
        "state IN ('not_sent','refused','accepted','completed','unknown')", name="effect_state"
    ),
)

attempts = Table(
    "system_effect_attempts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("intent_id", String(64), nullable=False, index=True),
    Column("attempt", Integer, nullable=False),
    Column("action", String(16), nullable=False),
    Column("state", String(16), nullable=False),
    Column("receipt", Text, nullable=False),
    Column("external_id", String(200), nullable=False),
    Column("observed_at", Float, nullable=False),
)
