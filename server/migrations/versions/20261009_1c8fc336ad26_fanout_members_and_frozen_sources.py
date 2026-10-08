"""
扇出成员和固定来源

版本：1c8fc336ad26，上一版本：1020f2a6dc11，生成时间：2026-10-09 04:15:20.771018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "1c8fc336ad26"
down_revision: str | None = "1020f2a6dc11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 升级到本版本。
def upgrade() -> None:
    op.create_table(
        "pipeline_members",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("pipeline_id", sa.String(length=32), nullable=False),
        sa.Column("stage_id", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("phase_name", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("current_input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("history_json", sa.Text(), nullable=False),
        sa.Column("declarations_json", sa.Text(), nullable=False),
        sa.Column("wait_until", sa.Float(), nullable=True),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("module_version", sa.String(length=40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Float(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipeline_runs.id"],
            name=op.f("fk_pipeline_members_pipeline_id_pipeline_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["pipeline_stages.id"],
            name=op.f("fk_pipeline_members_stage_id_pipeline_stages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_members")),
    )
    with op.batch_alter_table("pipeline_members", schema=None) as batch_op:
        batch_op.create_index(
            "ix_pipeline_member_state", ["stage_id", "state", "key"], unique=False
        )
        batch_op.create_index("uq_pipeline_member", ["stage_id", "key"], unique=True)
        batch_op.create_index("uq_pipeline_member_job", ["job_id"], unique=True)

    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_schema_json", sa.Text(), nullable=True))
        batch_op.drop_index("uq_pipeline_active")
        batch_op.create_index(
            "uq_pipeline_active",
            ["org_id", "pipeline"],
            unique=True,
            sqlite_where=sa.text(
                "state IN ('running','waiting_external','waiting_members','unknown','version_blocked')"
            ),
            postgresql_where=sa.text(
                "state IN ('running','waiting_external','waiting_members','unknown','version_blocked')"
            ),
        )


# 回退到上一版本。
def downgrade() -> None:
    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.drop_column("source_schema_json")
        batch_op.drop_column("source_json")
        batch_op.drop_index("uq_pipeline_active")
        batch_op.create_index(
            "uq_pipeline_active",
            ["org_id", "pipeline"],
            unique=True,
            sqlite_where=sa.text(
                "state IN ('running','waiting_external','unknown','version_blocked')"
            ),
            postgresql_where=sa.text(
                "state IN ('running','waiting_external','unknown','version_blocked')"
            ),
        )

    with op.batch_alter_table("pipeline_members", schema=None) as batch_op:
        batch_op.drop_index("uq_pipeline_member_job")
        batch_op.drop_index("uq_pipeline_member")
        batch_op.drop_index("ix_pipeline_member_state")

    op.drop_table("pipeline_members")
