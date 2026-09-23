"""
旧系统表的独立元数据。迁移模块在这里声明旧表，不进入本系统的迁移。
"""

from sqlalchemy import MetaData

legacy_metadata = MetaData()
