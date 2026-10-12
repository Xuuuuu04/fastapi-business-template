"""
任务排队与业务有效期、串行顺序、跨worker资源；只增加结构，不领取或重发历史任务。

版本：e30a00000007，上一版本：e30a00000006。
"""

import sqlalchemy as sa
from alembic import op

revision = "e30a00000007"
down_revision = "e30a00000006"
branch_labels = None
depends_on = None


# 旧任务未声明约束，保留空字段，不推定历史业务键和有效期。
def upgrade() -> None:
    op.add_column(
        "system_jobs",
        sa.Column("failed_attempts", sa.Integer(), nullable=True),
    )
    op.add_column("system_jobs", sa.Column("serial_key", sa.String(64), nullable=True))
    op.add_column("system_jobs", sa.Column("serial_position", sa.Integer(), nullable=True))
    op.add_column("system_jobs", sa.Column("queued_until", sa.Float(), nullable=True))
    op.add_column("system_jobs", sa.Column("valid_until", sa.Float(), nullable=True))
    op.create_index("ix_system_jobs_serial_key", "system_jobs", ["serial_key"])
    op.create_table(
        "system_resource_pools",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("cooldown_until", sa.Float(), nullable=False),
        sa.Column("next_position", sa.Integer(), nullable=False),
    )
    op.create_table(
        "system_resource_leases",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("pool_id", sa.String(64), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
        sa.Column("cooldown", sa.Float(), nullable=False),
    )
    op.create_index("ix_system_resource_leases_pool_id", "system_resource_leases", ["pool_id"])
    op.create_index("ix_system_resource_leases_owner", "system_resource_leases", ["owner"])


# 降级删除本版本约束，执行前先停止worker并处理在途任务。
def downgrade() -> None:
    op.drop_index("ix_system_resource_leases_owner", table_name="system_resource_leases")
    op.drop_index("ix_system_resource_leases_pool_id", table_name="system_resource_leases")
    op.drop_table("system_resource_leases")
    op.drop_table("system_resource_pools")
    op.drop_index("ix_system_jobs_serial_key", table_name="system_jobs")
    with op.batch_alter_table("system_jobs") as batch:
        for name in (
            "valid_until",
            "queued_until",
            "serial_position",
            "serial_key",
            "failed_attempts",
        ):
            batch.drop_column(name)
