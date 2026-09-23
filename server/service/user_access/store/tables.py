"""
用户权限模块独占的组织、角色和用户表。
"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint

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
    Column("password_hash", String(192), nullable=False),
    Column("role_id", Integer, ForeignKey("user_access_roles.id"), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    UniqueConstraint("org_id", "username", name="uq_user_access_username"),
)
