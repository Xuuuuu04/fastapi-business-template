"""
任务表和排队计数表。任务表本身就是队列：worker 从这里领取任务。
时间列保存 Unix 秒数（浮点数），在 SQLite 和 PostgreSQL 上比较方式一致。
"""

from sqlalchemy import Column, Float, Index, Integer, String, Table, Text, text

from shared.db.tables import metadata

jobs = Table(
    "system_jobs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("contract", String(120), nullable=False),
    Column("module_version", String(40), nullable=False),
    Column("state", String(20), nullable=False),
    Column("input_json", Text, nullable=False),
    Column("input_hash", String(64), nullable=False),
    Column("caller_json", Text, nullable=False),
    Column("key_scope", String(120), nullable=False, default=""),
    Column("key", String(120), nullable=True),
    Column("attempt", Integer, nullable=False, default=0),
    Column("run_after", Float, nullable=False),
    Column("lease_until", Float, nullable=True),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("finished_at", Float, nullable=True),
    Column("request_id", String(64), nullable=False, default=""),
    Column("last_run_id", String(32), nullable=False, default=""),
    Column("error_code", String(60), nullable=False, default=""),
    Column("error_message", Text, nullable=False, default=""),
    Column("result_json", Text, nullable=True),
    Index("ix_system_jobs_ready", "state", "run_after"),
    Index(
        "uq_system_jobs_key",
        "contract",
        "key_scope",
        "key",
        unique=True,
        sqlite_where=text("key IS NOT NULL"),
        postgresql_where=text("key IS NOT NULL"),
    ),
)

job_counts = Table(
    "system_job_counts",
    metadata,
    Column("contract", String(120), primary_key=True),
    Column("active", Integer, nullable=False, default=0),
)
