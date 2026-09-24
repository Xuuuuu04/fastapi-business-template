"""
用户权限模块独占的组织、角色、用户、刷新令牌和密码重置码表。
两步验证密钥（R-09）用 APP_DATA_KEYS 加密后保存；重置码（R-08）与刷新令牌一样只保存摘要。
刷新令牌只保存 SHA-256 摘要；同一次登录后轮换出的令牌共用一个 family_id，可以整组作废。
"""

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

from shared.public import metadata

orgs = Table(
    "user_access_orgs",
    metadata,
    Column("code", String(32), primary_key=True),
    Column("name", String(80), nullable=False),
)

roles = Table(
    "user_access_roles",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("org_id", String(32), ForeignKey("user_access_orgs.code"), nullable=False),
    Column("name", String(64), nullable=False),
    Column("permissions", Text, nullable=False),
    UniqueConstraint("org_id", "name", name="uq_user_access_role_name"),
)

users = Table(
    "user_access_users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("org_id", String(32), ForeignKey("user_access_orgs.code"), nullable=False),
    Column("username", String(64), nullable=False),
    Column("password_hash", String(192), nullable=False, info={"secret": True}),
    Column("role_id", Integer, ForeignKey("user_access_roles.id"), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("otp_secret", Text, nullable=True, info={"secret": True}),
    Column("otp_enabled", Boolean, nullable=False, default=False, server_default=text("false")),
    Column("otp_last_step", Integer, nullable=True),
    UniqueConstraint("org_id", "username", name="uq_user_access_username"),
)

reset_codes = Table(
    "user_access_reset_codes",
    metadata,
    Column("code_sha256", String(64), primary_key=True),
    Column("org_id", String(32), ForeignKey("user_access_orgs.code"), nullable=False),
    Column("user_id", Integer, ForeignKey("user_access_users.id"), nullable=False, index=True),
    Column("created_by", String(120), nullable=False),
    Column("expires_at", Float, nullable=False),
    Column("used_at", Float, nullable=True),
)

refresh_tokens = Table(
    "user_access_refresh_tokens",
    metadata,
    Column("token_sha256", String(64), primary_key=True),
    Column("family_id", String(32), nullable=False, index=True),
    Column("org_id", String(32), ForeignKey("user_access_orgs.code"), nullable=False),
    Column("user_id", Integer, ForeignKey("user_access_users.id"), nullable=False, index=True),
    Column("started_at", Float, nullable=False),
    Column("expires_at", Float, nullable=False, index=True),
    Column("used_at", Float, nullable=True),
    Column("revoked_at", Float, nullable=True),
)
