"""
检查数据库结构是否已经迁移到代码需要的版本。
迁移只由部署步骤执行（uv run alembic upgrade head），服务启动时不自动修改表结构。
"""

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shared.db.database import Database

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


# 读取迁移脚本中的最新版本号。
def head_revision() -> str:
    head = ScriptDirectory(str(MIGRATIONS)).get_current_head()
    return head or ""


# 读取数据库当前的迁移版本号；还没有迁移时返回空字符串。
async def current_revision(database: Database) -> str:
    try:
        async with database.read() as connection:
            value = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    except DBAPIError:
        return ""
    return str(value or "")
