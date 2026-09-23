"""
add common capabilities

版本：285d000e79bc，上一版本：5b8041ffc18a，生成时间：2026-09-24 01:06:31.797570
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import shared.db.types

revision: str = '285d000e79bc'
down_revision: str | None = '5b8041ffc18a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 升级到本版本。
def upgrade() -> None:
    op.create_table('file_library_files',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('org_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('content_type', sa.String(length=120), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('created_at', shared.db.types.UtcTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_file_library_files'))
    )
    with op.batch_alter_table('file_library_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_file_library_files_org_id'), ['org_id'], unique=False)

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

    op.create_table('user_access_orgs',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_user_access_orgs'))
    )
    op.create_table('user_access_roles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('permissions', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['user_access_orgs.code'], name=op.f('fk_user_access_roles_org_id_user_access_orgs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_access_roles')),
    sa.UniqueConstraint('org_id', 'name', name='uq_user_access_role_name')
    )
    op.create_table('user_access_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=192), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['user_access_orgs.code'], name=op.f('fk_user_access_users_org_id_user_access_orgs')),
    sa.ForeignKeyConstraint(['role_id'], ['user_access_roles.id'], name=op.f('fk_user_access_users_role_id_user_access_roles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_access_users')),
    sa.UniqueConstraint('org_id', 'username', name='uq_user_access_username')
    )


# 回退到上一版本。
def downgrade() -> None:
    op.drop_table('user_access_users')
    op.drop_table('user_access_roles')
    op.drop_table('user_access_orgs')
    with op.batch_alter_table('system_audit_records', schema=None) as batch_op:
        batch_op.drop_index('ix_system_audit_org')
        batch_op.drop_index('ix_system_audit_created')

    op.drop_table('system_audit_records')
    with op.batch_alter_table('file_library_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_file_library_files_org_id'))

    op.drop_table('file_library_files')
