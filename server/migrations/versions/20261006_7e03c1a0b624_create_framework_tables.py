"""
create framework tables

仅用于新项目空数据库；只创建公共框架表。已有项目保留自己的迁移历史。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e03c1a0b624"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 升级到本版本。
def upgrade() -> None:
    create_actions()
    create_changes()
    create_counts()
    create_jobs()
    create_runs()


# 保存操作记录。
def create_actions() -> None:
    op.create_table(
        "system_audit_records",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_audit_records")),
    )
    with op.batch_alter_table("system_audit_records", schema=None) as batch_op:
        batch_op.create_index("ix_system_audit_created", ["created_at"], unique=False)
        batch_op.create_index("ix_system_audit_org", ["org_id", "created_at"], unique=False)


# 保存字段变化。
def create_changes() -> None:
    op.create_table(
        "system_change_history",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("table_name", sa.String(length=80), nullable=False),
        sa.Column("record_key", sa.String(length=80), nullable=False),
        sa.Column("field", sa.String(length=80), nullable=False),
        sa.Column("before", sa.Text(), nullable=False),
        sa.Column("after", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_change_history")),
    )
    with op.batch_alter_table("system_change_history", schema=None) as batch_op:
        batch_op.create_index("ix_system_change_org", ["org_id", "created_at"], unique=False)
        batch_op.create_index(
            "ix_system_change_record", ["table_name", "record_key", "created_at"], unique=False
        )


# 保存任务数量。
def create_counts() -> None:
    op.create_table(
        "system_job_counts",
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("contract", name=op.f("pk_system_job_counts")),
    )


# 保存后台任务。
def create_jobs() -> None:
    op.create_table(
        "system_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("module_version", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("caller_json", sa.Text(), nullable=False),
        sa.Column("key_scope", sa.String(length=120), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.Float(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("last_run_id", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_jobs")),
    )
    with op.batch_alter_table("system_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_system_jobs_ready", ["state", "run_after"], unique=False)
        batch_op.create_index(
            "uq_system_jobs_key",
            ["contract", "key_scope", "key"],
            unique=True,
            sqlite_where=sa.text("key IS NOT NULL"),
            postgresql_where=sa.text("key IS NOT NULL"),
        )


# 保存运行过程。
def create_runs() -> None:
    op.create_table(
        "system_run_records",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("root_id", sa.String(length=32), nullable=False),
        sa.Column("parent_id", sa.String(length=32), nullable=False),
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("elapsed_ms", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_run_records")),
    )
    with op.batch_alter_table("system_run_records", schema=None) as batch_op:
        batch_op.create_index(
            "ix_system_run_records_module", ["module", "started_at"], unique=False
        )
        batch_op.create_index("ix_system_run_records_root", ["root_id"], unique=False)
        batch_op.create_index("ix_system_run_records_started", ["started_at"], unique=False)


# 回退到上一版本。
def downgrade() -> None:
    with op.batch_alter_table("system_run_records", schema=None) as batch_op:
        batch_op.drop_index("ix_system_run_records_started")
        batch_op.drop_index("ix_system_run_records_root")
        batch_op.drop_index("ix_system_run_records_module")

    op.drop_table("system_run_records")
    with op.batch_alter_table("system_jobs", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_system_jobs_key",
            sqlite_where=sa.text("key IS NOT NULL"),
            postgresql_where=sa.text("key IS NOT NULL"),
        )
        batch_op.drop_index("ix_system_jobs_ready")

    op.drop_table("system_jobs")
    op.drop_table("system_job_counts")
    with op.batch_alter_table("system_change_history", schema=None) as batch_op:
        batch_op.drop_index("ix_system_change_record")
        batch_op.drop_index("ix_system_change_org")

    op.drop_table("system_change_history")
    with op.batch_alter_table("system_audit_records", schema=None) as batch_op:
        batch_op.drop_index("ix_system_audit_org")
        batch_op.drop_index("ix_system_audit_created")

    op.drop_table("system_audit_records")
