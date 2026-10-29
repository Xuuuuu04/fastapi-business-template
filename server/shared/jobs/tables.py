"""
任务表和排队计数表。任务表本身就是队列：worker 从这里领取任务。
时间列保存 Unix 秒数（浮点数），在 SQLite 和 PostgreSQL 上比较方式一致。
"""

from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, String, Table, Text, text

from shared.db.tables import metadata
from shared.operations import tables as operations_tables
from shared.pipelines import tables as pipeline_tables

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
    Column("failed_attempts", Integer, nullable=True, default=0),
    Column("serial_key", String(64), nullable=True, index=True),
    Column("serial_position", Integer, nullable=True),
    Column("queued_until", Float, nullable=True),
    Column("valid_until", Float, nullable=True),
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

# 每个分段任务的当前恢复位置及在途外部写入证明；与业务段一起提交。
checkpoints = Table(
    "system_job_checkpoints",
    metadata,
    Column(
        "job_id", String(32), ForeignKey("system_jobs.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("number", Integer, nullable=False),
    Column("cursor_json", Text, nullable=False),
    Column("total_rows", Integer, nullable=False),
    Column("external_pending", Boolean, nullable=False),
)

# 每个已提交段的独立运行编号、行数和耗时，崩溃后仍可查看。
segments = Table(
    "system_job_segments",
    metadata,
    Column(
        "job_id", String(32), ForeignKey("system_jobs.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("number", Integer, primary_key=True),
    Column("attempt", Integer, nullable=False),
    Column("run_id", String(32), nullable=False),
    Column("cursor_json", Text, nullable=False),
    Column("rows", Integer, nullable=False),
    Column("total_rows", Integer, nullable=False),
    Column("elapsed_ms", Float, nullable=False),
    Column("committed_at", Float, nullable=False),
)
