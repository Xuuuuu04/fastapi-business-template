from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shared.db.database import Database

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def head_revision() -> str:
    head = ScriptDirectory(str(MIGRATIONS)).get_current_head()
    return head or ""


async def current_revision(database: Database) -> str:
    try:
        async with database.read() as connection:
            value = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    except DBAPIError:
        return ""
    return str(value or "")
