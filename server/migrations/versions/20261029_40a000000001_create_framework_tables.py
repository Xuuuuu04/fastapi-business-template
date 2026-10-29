"""
建立框架表。

版本：40a000000001，全新数据库的第一个版本。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import shared.db.types

revision: str = '40a000000001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    sa.Column('source_json', sa.Text(), nullable=True),
    sa.Column('source_schema_json', sa.Text(), nullable=True),
    sa.Column('caller_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('complete_by', sa.Float(), nullable=True),
    sa.Column('overdue', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('overdue_at', sa.Float(), nullable=True),
    sa.Column('on_overdue', sa.String(length=12), server_default='continue', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pipeline_runs'))
    )
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.create_index('ix_pipeline_waiting', ['pipeline', 'org_id', 'state', 'created_at'], unique=False)
        batch_op.create_index('uq_pipeline_active', ['org_id', 'pipeline'], unique=True, sqlite_where=sa.text("state IN ('running','waiting_external','waiting_members','overdue_paused','unknown','version_blocked')"), postgresql_where=sa.text("state IN ('running','waiting_external','waiting_members','overdue_paused','unknown','version_blocked')"))
        batch_op.create_index('uq_pipeline_cycle', ['org_id', 'pipeline', 'cycle_key'], unique=True)

    op.create_table('system_audit_records',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('actor', sa.String(length=120), nullable=False),
    sa.Column('org_id', sa.String(length=64), nullable=False),
    sa.Column('contract', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_audit_records'))
    )
    with op.batch_alter_table('system_audit_records', schema=None) as batch_op:
        batch_op.create_index('ix_system_audit_created', ['created_at'], unique=False)
        batch_op.create_index('ix_system_audit_org', ['org_id', 'created_at'], unique=False)

    op.create_table('system_change_history',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('table_name', sa.String(length=80), nullable=False),
    sa.Column('record_key', sa.String(length=80), nullable=False),
    sa.Column('field', sa.String(length=80), nullable=False),
    sa.Column('before', sa.Text(), nullable=False),
    sa.Column('after', sa.Text(), nullable=False),
    sa.Column('actor', sa.String(length=120), nullable=False),
    sa.Column('org_id', sa.String(length=64), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_change_history'))
    )
    with op.batch_alter_table('system_change_history', schema=None) as batch_op:
        batch_op.create_index('ix_system_change_org', ['org_id', 'created_at'], unique=False)
        batch_op.create_index('ix_system_change_record', ['table_name', 'record_key', 'created_at'], unique=False)

    op.create_table('system_effect_attempts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('intent_id', sa.String(length=64), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=16), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('receipt', sa.Text(), nullable=False),
    sa.Column('external_id', sa.String(length=200), nullable=False),
    sa.Column('observed_at', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_effect_attempts'))
    )
    with op.batch_alter_table('system_effect_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_effect_attempts_intent_id'), ['intent_id'], unique=False)

    op.create_table('system_effect_intents',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=160), nullable=False),
    sa.Column('owner', sa.String(length=64), nullable=False),
    sa.Column('protocol', sa.String(length=64), nullable=False),
    sa.Column('binding', sa.String(length=64), nullable=False),
    sa.Column('input_digest', sa.String(length=64), nullable=False),
    sa.Column('request', sa.Text(), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('receipt', sa.Text(), nullable=False),
    sa.Column('external_id', sa.String(length=200), nullable=False),
    sa.Column('simulated', sa.Boolean(), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('lease_until', sa.Float(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.CheckConstraint("state IN ('not_sent','refused','accepted','completed','unknown')", name=op.f('ck_system_effect_intents_effect_state')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_effect_intents'))
    )
    op.create_table('system_job_counts',
    sa.Column('contract', sa.String(length=120), nullable=False),
    sa.Column('active', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('contract', name=op.f('pk_system_job_counts'))
    )
    op.create_table('system_jobs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('contract', sa.String(length=120), nullable=False),
    sa.Column('module_version', sa.String(length=40), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('input_json', sa.Text(), nullable=False),
    sa.Column('input_hash', sa.String(length=64), nullable=False),
    sa.Column('caller_json', sa.Text(), nullable=False),
    sa.Column('key_scope', sa.String(length=120), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('failed_attempts', sa.Integer(), nullable=True),
    sa.Column('serial_key', sa.String(length=64), nullable=True),
    sa.Column('serial_position', sa.Integer(), nullable=True),
    sa.Column('queued_until', sa.Float(), nullable=True),
    sa.Column('valid_until', sa.Float(), nullable=True),
    sa.Column('run_after', sa.Float(), nullable=False),
    sa.Column('lease_until', sa.Float(), nullable=True),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=False),
    sa.Column('last_run_id', sa.String(length=32), nullable=False),
    sa.Column('error_code', sa.String(length=60), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=False),
    sa.Column('result_json', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_jobs'))
    )
    with op.batch_alter_table('system_jobs', schema=None) as batch_op:
        batch_op.create_index('ix_system_jobs_ready', ['state', 'run_after'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_jobs_serial_key'), ['serial_key'], unique=False)
        batch_op.create_index('uq_system_jobs_key', ['contract', 'key_scope', 'key'], unique=True, sqlite_where=sa.text('key IS NOT NULL'), postgresql_where=sa.text('key IS NOT NULL'))

    op.create_table('system_notifications',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('sent_at', sa.Float(), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_notifications'))
    )
    with op.batch_alter_table('system_notifications', schema=None) as batch_op:
        batch_op.create_index('ix_system_notification_pending', ['state', 'created_at'], unique=False)
        batch_op.create_index('uq_system_notification', ['kind', 'key'], unique=True)

    op.create_table('system_resource_leases',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('pool_id', sa.String(length=64), nullable=False),
    sa.Column('owner', sa.String(length=64), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('lease_until', sa.Float(), nullable=False),
    sa.Column('cooldown', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_resource_leases'))
    )
    with op.batch_alter_table('system_resource_leases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_resource_leases_owner'), ['owner'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_resource_leases_pool_id'), ['pool_id'], unique=False)

    op.create_table('system_resource_pools',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('cooldown_until', sa.Float(), nullable=False),
    sa.Column('next_position', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_resource_pools'))
    )
    op.create_table('system_run_records',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('root_id', sa.String(length=32), nullable=False),
    sa.Column('parent_id', sa.String(length=32), nullable=False),
    sa.Column('contract', sa.String(length=120), nullable=False),
    sa.Column('module', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=False),
    sa.Column('job_id', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.Float(), nullable=False),
    sa.Column('elapsed_ms', sa.Float(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_run_records'))
    )
    with op.batch_alter_table('system_run_records', schema=None) as batch_op:
        batch_op.create_index('ix_system_run_records_module', ['module', 'started_at'], unique=False)
        batch_op.create_index('ix_system_run_records_root', ['root_id'], unique=False)
        batch_op.create_index('ix_system_run_records_started', ['started_at'], unique=False)

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

    op.create_table('system_job_checkpoints',
    sa.Column('job_id', sa.String(length=32), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('cursor_json', sa.Text(), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('external_pending', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['system_jobs.id'], name=op.f('fk_system_job_checkpoints_job_id_system_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_id', name=op.f('pk_system_job_checkpoints'))
    )
    op.create_table('system_job_segments',
    sa.Column('job_id', sa.String(length=32), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('cursor_json', sa.Text(), nullable=False),
    sa.Column('rows', sa.Integer(), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('elapsed_ms', sa.Float(), nullable=False),
    sa.Column('committed_at', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['system_jobs.id'], name=op.f('fk_system_job_segments_job_id_system_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_id', 'number', name=op.f('pk_system_job_segments'))
    )
    op.create_table('pipeline_members',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('pipeline_id', sa.String(length=32), nullable=False),
    sa.Column('stage_id', sa.String(length=32), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('state', sa.String(length=24), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('phase_name', sa.String(length=64), nullable=False),
    sa.Column('job_id', sa.String(length=32), nullable=True),
    sa.Column('input_json', sa.Text(), nullable=False),
    sa.Column('current_input_json', sa.Text(), nullable=False),
    sa.Column('output_json', sa.Text(), nullable=True),
    sa.Column('history_json', sa.Text(), nullable=False),
    sa.Column('declarations_json', sa.Text(), nullable=False),
    sa.Column('wait_until', sa.Float(), nullable=True),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('module_version', sa.String(length=40), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('elapsed_ms', sa.Float(), nullable=False),
    sa.Column('started_at', sa.Float(), nullable=True),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('accepted', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.Float(), nullable=False),
    sa.Column('finished_at', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['pipeline_id'], ['pipeline_runs.id'], name=op.f('fk_pipeline_members_pipeline_id_pipeline_runs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['stage_id'], ['pipeline_stages.id'], name=op.f('fk_pipeline_members_stage_id_pipeline_stages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pipeline_members'))
    )
    with op.batch_alter_table('pipeline_members', schema=None) as batch_op:
        batch_op.create_index('ix_pipeline_member_state', ['stage_id', 'state', 'key'], unique=False)
        batch_op.create_index('uq_pipeline_member', ['stage_id', 'key'], unique=True)
        batch_op.create_index('uq_pipeline_member_job', ['job_id'], unique=True)



def downgrade() -> None:
    with op.batch_alter_table('pipeline_members', schema=None) as batch_op:
        batch_op.drop_index('uq_pipeline_member_job')
        batch_op.drop_index('uq_pipeline_member')
        batch_op.drop_index('ix_pipeline_member_state')

    op.drop_table('pipeline_members')
    op.drop_table('system_job_segments')
    op.drop_table('system_job_checkpoints')
    with op.batch_alter_table('pipeline_stages', schema=None) as batch_op:
        batch_op.drop_index('uq_pipeline_stage_job')
        batch_op.drop_index('uq_pipeline_stage')

    op.drop_table('pipeline_stages')
    with op.batch_alter_table('system_run_records', schema=None) as batch_op:
        batch_op.drop_index('ix_system_run_records_started')
        batch_op.drop_index('ix_system_run_records_root')
        batch_op.drop_index('ix_system_run_records_module')

    op.drop_table('system_run_records')
    op.drop_table('system_resource_pools')
    with op.batch_alter_table('system_resource_leases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_resource_leases_pool_id'))
        batch_op.drop_index(batch_op.f('ix_system_resource_leases_owner'))

    op.drop_table('system_resource_leases')
    with op.batch_alter_table('system_notifications', schema=None) as batch_op:
        batch_op.drop_index('uq_system_notification')
        batch_op.drop_index('ix_system_notification_pending')

    op.drop_table('system_notifications')
    with op.batch_alter_table('system_jobs', schema=None) as batch_op:
        batch_op.drop_index('uq_system_jobs_key', sqlite_where=sa.text('key IS NOT NULL'), postgresql_where=sa.text('key IS NOT NULL'))
        batch_op.drop_index(batch_op.f('ix_system_jobs_serial_key'))
        batch_op.drop_index('ix_system_jobs_ready')

    op.drop_table('system_jobs')
    op.drop_table('system_job_counts')
    op.drop_table('system_effect_intents')
    with op.batch_alter_table('system_effect_attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_effect_attempts_intent_id'))

    op.drop_table('system_effect_attempts')
    with op.batch_alter_table('system_change_history', schema=None) as batch_op:
        batch_op.drop_index('ix_system_change_record')
        batch_op.drop_index('ix_system_change_org')

    op.drop_table('system_change_history')
    with op.batch_alter_table('system_audit_records', schema=None) as batch_op:
        batch_op.drop_index('ix_system_audit_org')
        batch_op.drop_index('ix_system_audit_created')

    op.drop_table('system_audit_records')
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.drop_index('uq_pipeline_cycle')
        batch_op.drop_index('uq_pipeline_active', sqlite_where=sa.text("state IN ('running','waiting_external','waiting_members','overdue_paused','unknown','version_blocked')"), postgresql_where=sa.text("state IN ('running','waiting_external','waiting_members','overdue_paused','unknown','version_blocked')"))
        batch_op.drop_index('ix_pipeline_waiting')

    op.drop_table('pipeline_runs')
