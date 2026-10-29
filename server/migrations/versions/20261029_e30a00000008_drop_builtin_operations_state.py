"""删除内置运维的状态表。

版本：e30a00000008，上一版本：e30a00000007。
"""

import sqlalchemy as sa
from alembic import op

revision = "e30a00000008"
down_revision = "e30a00000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("system_ops_state")


def downgrade() -> None:
    op.create_table(
        "system_ops_state",
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
