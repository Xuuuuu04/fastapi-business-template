"""
流程运行和阶段记录，两张新增框架表

版本：1020f2a6dc11，上一版本：a8c42f910d37，生成时间：2026-10-09 02:47:37.339933
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '1020f2a6dc11'
down_revision: str | None = 'a8c42f910d37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 升级到本版本。
def upgrade() -> None:
    op.create_table('pipeline_runs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('pipeline', sa.String(length=120), nullable=False),
    sa.Column('org_id', sa.String(length=64), nullable=False),
    sa.Column('cycle_key', sa.String(length=120), nullable=False),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('current_stage', sa.String(length=64), nullable=False),
    sa.Column('input_json', sa.Text(), nullable=False),
    sa.Column('declarations_json', sa.Text(), nullable=False),
    sa.Column('caller_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pipeline_runs'))
    )
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.create_index('ix_pipeline_waiting', ['pipeline', 'org_id', 'state', 'created_at'], unique=False)
        batch_op.create_index('uq_pipeline_active', ['org_id', 'pipeline'], unique=True, sqlite_where=sa.text("state IN ('running','waiting_external','unknown','version_blocked')"), postgresql_where=sa.text("state IN ('running','waiting_external','unknown','version_blocked')"))
        batch_op.create_index('uq_pipeline_cycle', ['org_id', 'pipeline', 'cycle_key'], unique=True)

    op.create_table('pipeline_stages',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('pipeline_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('contract', sa.String(length=120), nullable=False),
    sa.Column('job_id', sa.String(length=32), nullable=False),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('input_json', sa.Text(), nullable=False),
    sa.Column('output_json', sa.Text(), nullable=True),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('module_version', sa.String(length=40), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('poll_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('started_at', sa.Float(), nullable=True),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.Column('wait_until', sa.Float(), nullable=True),
    sa.Column('elapsed_ms', sa.Float(), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['pipeline_id'], ['pipeline_runs.id'], name=op.f('fk_pipeline_stages_pipeline_id_pipeline_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pipeline_stages'))
    )
    with op.batch_alter_table('pipeline_stages', schema=None) as batch_op:
        batch_op.create_index('uq_pipeline_stage', ['pipeline_id', 'name'], unique=True)
        batch_op.create_index('uq_pipeline_stage_job', ['job_id'], unique=True)



# 回退到上一版本。
def downgrade() -> None:
    with op.batch_alter_table('pipeline_stages', schema=None) as batch_op:
        batch_op.drop_index('uq_pipeline_stage_job')
        batch_op.drop_index('uq_pipeline_stage')

    op.drop_table('pipeline_stages')
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.drop_index('uq_pipeline_cycle')
        batch_op.drop_index('uq_pipeline_active', sqlite_where=sa.text("state IN ('running','waiting_external','unknown','version_blocked')"), postgresql_where=sa.text("state IN ('running','waiting_external','unknown','version_blocked')"))
        batch_op.drop_index('ix_pipeline_waiting')

    op.drop_table('pipeline_runs')
