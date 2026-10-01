"""
create framework tables

版本：fb7f89fe8685，上一版本：，生成时间：2026-10-01 19:01:50.807422
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import shared.db.types

revision: str = "fb7f89fe8685"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 升级到本版本。
def upgrade() -> None:
    create_files()
    create_actions()
    create_changes()
    create_counts()
    create_jobs()
    create_runs()
    create_orgs()
    create_roles()
    create_users()
    create_tokens()
    create_codes()


# 保存文件信息。
def create_files() -> None:
    op.create_table(
        "file_library_files",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("created_at", shared.db.types.UtcTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_library_files")),
    )
    with op.batch_alter_table("file_library_files", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_file_library_files_org_id"), ["org_id"], unique=False)


# 保存操作记录。
def create_actions() -> None:
    op.create_table(
        "system_audit_records",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_audit_records")),
    )
    with op.batch_alter_table("system_audit_records", schema=None) as batch_op:
        batch_op.create_index("ix_system_audit_created", ["created_at"], unique=False)
        batch_op.create_index("ix_system_audit_org", ["org_id", "created_at"], unique=False)


# 保存字段变化。
def create_changes() -> None:
    op.create_table(
        "system_change_history",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("table_name", sa.String(length=80), nullable=False),
        sa.Column("record_key", sa.String(length=80), nullable=False),
        sa.Column("field", sa.String(length=80), nullable=False),
        sa.Column("before", sa.Text(), nullable=False),
        sa.Column("after", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_change_history")),
    )
    with op.batch_alter_table("system_change_history", schema=None) as batch_op:
        batch_op.create_index("ix_system_change_org", ["org_id", "created_at"], unique=False)
        batch_op.create_index(
            "ix_system_change_record", ["table_name", "record_key", "created_at"], unique=False
        )


# 保存任务数量。
def create_counts() -> None:
    op.create_table(
        "system_job_counts",
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("contract", name=op.f("pk_system_job_counts")),
    )


# 保存后台任务。
def create_jobs() -> None:
    op.create_table(
        "system_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("module_version", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("caller_json", sa.Text(), nullable=False),
        sa.Column("key_scope", sa.String(length=120), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.Float(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("last_run_id", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_jobs")),
    )
    with op.batch_alter_table("system_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_system_jobs_ready", ["state", "run_after"], unique=False)
        batch_op.create_index(
            "uq_system_jobs_key",
            ["contract", "key_scope", "key"],
            unique=True,
            sqlite_where=sa.text("key IS NOT NULL"),
            postgresql_where=sa.text("key IS NOT NULL"),
        )


# 保存运行过程。
def create_runs() -> None:
    op.create_table(
        "system_run_records",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("root_id", sa.String(length=32), nullable=False),
        sa.Column("parent_id", sa.String(length=32), nullable=False),
        sa.Column("contract", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("elapsed_ms", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_run_records")),
    )
    with op.batch_alter_table("system_run_records", schema=None) as batch_op:
        batch_op.create_index(
            "ix_system_run_records_module", ["module", "started_at"], unique=False
        )
        batch_op.create_index("ix_system_run_records_root", ["root_id"], unique=False)
        batch_op.create_index("ix_system_run_records_started", ["started_at"], unique=False)


# 保存组织。
def create_orgs() -> None:
    op.create_table(
        "user_access_orgs",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_user_access_orgs")),
    )


# 保存角色权限。
def create_roles() -> None:
    op.create_table(
        "user_access_roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("permissions", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["user_access_orgs.code"],
            name=op.f("fk_user_access_roles_org_id_user_access_orgs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_access_roles")),
        sa.UniqueConstraint("org_id", "name", name="uq_user_access_role_name"),
    )


# 保存用户。
def create_users() -> None:
    op.create_table(
        "user_access_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(length=32), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=192), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("otp_secret", sa.Text(), nullable=True),
        sa.Column("otp_enabled", sa.Boolean(), server_default=sa.text("(false)"), nullable=False),
        sa.Column("otp_last_step", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["user_access_orgs.code"],
            name=op.f("fk_user_access_users_org_id_user_access_orgs"),
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["user_access_roles.id"],
            name=op.f("fk_user_access_users_role_id_user_access_roles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_access_users")),
        sa.UniqueConstraint("org_id", "username", name="uq_user_access_username"),
    )


# 保存登录刷新令牌。
def create_tokens() -> None:
    op.create_table(
        "user_access_refresh_tokens",
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=32), nullable=False),
        sa.Column("org_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("used_at", sa.Float(), nullable=True),
        sa.Column("revoked_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["user_access_orgs.code"],
            name=op.f("fk_user_access_refresh_tokens_org_id_user_access_orgs"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_access_users.id"],
            name=op.f("fk_user_access_refresh_tokens_user_id_user_access_users"),
        ),
        sa.PrimaryKeyConstraint("token_sha256", name=op.f("pk_user_access_refresh_tokens")),
    )
    with op.batch_alter_table("user_access_refresh_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_access_refresh_tokens_expires_at"), ["expires_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_user_access_refresh_tokens_family_id"), ["family_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_user_access_refresh_tokens_user_id"), ["user_id"], unique=False
        )


# 保存密码重置码。
def create_codes() -> None:
    op.create_table(
        "user_access_reset_codes",
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("used_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["user_access_orgs.code"],
            name=op.f("fk_user_access_reset_codes_org_id_user_access_orgs"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_access_users.id"],
            name=op.f("fk_user_access_reset_codes_user_id_user_access_users"),
        ),
        sa.PrimaryKeyConstraint("code_sha256", name=op.f("pk_user_access_reset_codes")),
    )
    with op.batch_alter_table("user_access_reset_codes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_access_reset_codes_user_id"), ["user_id"], unique=False
        )


# 回退到上一版本。
def downgrade() -> None:
    with op.batch_alter_table("user_access_reset_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_access_reset_codes_user_id"))

    op.drop_table("user_access_reset_codes")
    with op.batch_alter_table("user_access_refresh_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_access_refresh_tokens_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_access_refresh_tokens_family_id"))
        batch_op.drop_index(batch_op.f("ix_user_access_refresh_tokens_expires_at"))

    op.drop_table("user_access_refresh_tokens")
    op.drop_table("user_access_users")
    op.drop_table("user_access_roles")
    op.drop_table("user_access_orgs")
    with op.batch_alter_table("system_run_records", schema=None) as batch_op:
        batch_op.drop_index("ix_system_run_records_started")
        batch_op.drop_index("ix_system_run_records_root")
        batch_op.drop_index("ix_system_run_records_module")

    op.drop_table("system_run_records")
    with op.batch_alter_table("system_jobs", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_system_jobs_key",
            sqlite_where=sa.text("key IS NOT NULL"),
            postgresql_where=sa.text("key IS NOT NULL"),
        )
        batch_op.drop_index("ix_system_jobs_ready")

    op.drop_table("system_jobs")
    op.drop_table("system_job_counts")
    with op.batch_alter_table("system_change_history", schema=None) as batch_op:
        batch_op.drop_index("ix_system_change_record")
        batch_op.drop_index("ix_system_change_org")

    op.drop_table("system_change_history")
    with op.batch_alter_table("system_audit_records", schema=None) as batch_op:
        batch_op.drop_index("ix_system_audit_org")
        batch_op.drop_index("ix_system_audit_created")

    op.drop_table("system_audit_records")
    with op.batch_alter_table("file_library_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_file_library_files_org_id"))

    op.drop_table("file_library_files")
