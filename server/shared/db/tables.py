"""
全项目共用的表结构登记处 metadata。
各模块在自己的 store/tables.py 中用它定义表；迁移工具从这里读取全部表结构。
约束命名规则固定，保证迁移文件中的名字稳定、可读。
"""

from sqlalchemy import MetaData

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
