from sqlalchemy import Column, Float, Index, String, Table, Text

from shared.db.tables import metadata

run_records = Table(
    "system_run_records",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("root_id", String(32), nullable=False),
    Column("parent_id", String(32), nullable=False, default=""),
    Column("contract", String(120), nullable=False),
    Column("module", String(60), nullable=False),
    Column("status", String(20), nullable=False),
    Column("request_id", String(64), nullable=False, default=""),
    Column("job_id", String(32), nullable=False, default=""),
    Column("started_at", Float, nullable=False),
    Column("elapsed_ms", Float, nullable=False),
    Column("summary", Text, nullable=False),
    Column("body", Text, nullable=False),
    Index("ix_system_run_records_started", "started_at"),
    Index("ix_system_run_records_root", "root_id"),
    Index("ix_system_run_records_module", "module", "started_at"),
)
