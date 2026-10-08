"""
流程运行与阶段记录：周期去重、每组织同流程最多一条活动运行，阶段与后台任务一一关联。
"""

from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String, Table, Text, text

from shared.db.tables import metadata

runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("pipeline", String(120), nullable=False),
    Column("org_id", String(64), nullable=False),
    Column("cycle_key", String(120), nullable=False),
    Column("state", String(24), nullable=False),
    Column("current_stage", String(64), nullable=False),
    Column("input_json", Text, nullable=False),
    Column("declarations_json", Text, nullable=False),
    Column("caller_json", Text, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("finished_at", Float, nullable=True),
    Column("reason", Text, nullable=False),
    Index("uq_pipeline_cycle", "org_id", "pipeline", "cycle_key", unique=True),
    Index("ix_pipeline_waiting", "pipeline", "org_id", "state", "created_at"),
    Index(
        "uq_pipeline_active",
        "org_id",
        "pipeline",
        unique=True,
        sqlite_where=text("state IN ('running','waiting_external','unknown','version_blocked')"),
        postgresql_where=text(
            "state IN ('running','waiting_external','unknown','version_blocked')"
        ),
    ),
)

stages = Table(
    "pipeline_stages",
    metadata,
    Column("id", String(32), primary_key=True),
    Column(
        "pipeline_id",
        String(32),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(64), nullable=False),
    Column("position", Integer, nullable=False),
    Column("contract", String(120), nullable=False),
    Column("job_id", String(32), nullable=False),
    Column("state", String(24), nullable=False),
    Column("input_json", Text, nullable=False),
    Column("output_json", Text, nullable=True),
    Column("run_id", String(32), nullable=False),
    Column("module_version", String(40), nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("poll_count", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("started_at", Float, nullable=True),
    Column("finished_at", Float, nullable=True),
    Column("wait_until", Float, nullable=True),
    Column("elapsed_ms", Float, nullable=False),
    Column("error", Text, nullable=False),
    Index("uq_pipeline_stage", "pipeline_id", "name", unique=True),
    Index("uq_pipeline_stage_job", "job_id", unique=True),
)
