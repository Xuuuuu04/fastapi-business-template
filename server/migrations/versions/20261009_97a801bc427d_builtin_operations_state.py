"""跨worker内置运维容量状态。

Revision ID: 97a801bc427d
Revises: 74887aa86ebc
"""

import sqlalchemy as sa
from alembic import op

revision = "97a801bc427d"
down_revision = "74887aa86ebc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_ops_state",
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("system_ops_state")
