"""
流程截止时间、逾期事实和通知待发送队列

版本：74887aa86ebc，上一版本：1c8fc336ad26，生成时间：2026-10-09 04:41:09.240030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "74887aa86ebc"
down_revision: str | None = "1c8fc336ad26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 升级到本版本。
def upgrade() -> None:
    op.create_table(
        "system_notifications",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("sent_at", sa.Float(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_notifications")),
    )
    with op.batch_alter_table("system_notifications", schema=None) as batch_op:
        batch_op.create_index(
            "ix_system_notification_pending", ["state", "created_at"], unique=False
        )
        batch_op.create_index("uq_system_notification", ["kind", "key"], unique=True)

    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("complete_by", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("overdue", sa.Boolean(), server_default=sa.text("(false)"), nullable=False)
        )
        batch_op.add_column(sa.Column("overdue_at", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("on_overdue", sa.String(length=12), server_default="continue", nullable=False)
        )
        batch_op.drop_index("uq_pipeline_active")
        batch_op.create_index(
            "uq_pipeline_active",
            ["org_id", "pipeline"],
            unique=True,
            sqlite_where=sa.text(
                "state IN ('running','waiting_external','waiting_members','overdue_paused','unknown','version_blocked')"
            ),
            postgresql_where=sa.text(
                "state IN ('running','waiting_external','waiting_members','overdue_paused','unknown','version_blocked')"
            ),
        )


# 回退到上一版本。
def downgrade() -> None:
    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.drop_column("on_overdue")
        batch_op.drop_column("overdue_at")
        batch_op.drop_column("overdue")
        batch_op.drop_column("complete_by")
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

    with op.batch_alter_table("system_notifications", schema=None) as batch_op:
        batch_op.drop_index("uq_system_notification")
        batch_op.drop_index("ix_system_notification_pending")

    op.drop_table("system_notifications")
