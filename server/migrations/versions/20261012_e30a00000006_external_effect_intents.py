"""
持久外部意图和尝试回执；只增加结构，不读取或发送历史请求。

版本：e30a00000006，上一版本：97a801bc427d。
"""

import sqlalchemy as sa
from alembic import op

revision = "e30a00000006"
down_revision = "97a801bc427d"
branch_labels = None
depends_on = None


# 新增意图与证据，部署者显式运行迁移后才能调用外部效果。
def upgrade() -> None:
    create_intents()
    op.create_table(
        "system_effect_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("intent_id", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("receipt", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_system_effect_attempts_intent_id", "system_effect_attempts", ["intent_id"])


# 意图正文与回执加密，领取状态只存操作事实，不存凭据。
def create_intents() -> None:
    op.create_table(
        "system_effect_intents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(160), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("protocol", sa.String(64), nullable=False),
        sa.Column("binding", sa.String(64), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("receipt", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "state IN ('not_sent','refused','accepted','completed','unknown')", name="effect_state"
        ),
    )


# 降级只删除本版本的两张表，调用方先处理尚未确认的证据。
def downgrade() -> None:
    op.drop_index("ix_system_effect_attempts_intent_id", table_name="system_effect_attempts")
    op.drop_table("system_effect_attempts")
    op.drop_table("system_effect_intents")
