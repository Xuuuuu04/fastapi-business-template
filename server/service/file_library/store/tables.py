"""
文件记录表。组织列由框架检查，删除标记使下载立即不可用。
"""

from sqlalchemy import BigInteger, Column, Float, String, Table

from shared.public import UtcTime, metadata, org_column

files = Table(
    "file_library_files",
    metadata,
    Column("id", String(32), primary_key=True),
    org_column(),
    Column("name", String(200), nullable=False),
    Column("size", BigInteger, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("storage_key", String(300), nullable=False),
    Column("created_at", UtcTime(), nullable=False),
    Column("deleted_at", Float, nullable=True),
)
