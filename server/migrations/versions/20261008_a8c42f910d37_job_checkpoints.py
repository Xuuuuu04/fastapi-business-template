"""
新增分段任务恢复位置与段证据，不修改旧任务或业务表。
既有产品在自己的迁移链末端增加等效迁移，不替换迁移历史。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8c42f910d37"
down_revision: str | None = "7e03c1a0b624"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 添加框架分段状态表，历史任务无须修改。
def upgrade() -> None:
    op.create_table(
        "system_job_checkpoints",
        sa.Column("job_id", sa.String(32), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("cursor_json", sa.Text(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("external_pending", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["system_jobs.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "system_job_segments",
        sa.Column("job_id", sa.String(32), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("cursor_json", sa.Text(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Float(), nullable=False),
        sa.Column("committed_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["system_jobs.id"], ondelete="CASCADE"),
    )


# 仅撤销新增表，已提交的业务结果不会因回退被删除。
def downgrade() -> None:
    op.drop_table("system_job_segments")
    op.drop_table("system_job_checkpoints")
