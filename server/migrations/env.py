import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import shared.access.audit
import shared.db.history
import shared.jobs.tables
import shared.records.tables
from app.setup.application import application, application_modules
from shared.db.database import engine_options
from shared.db.ownership import ownership
from shared.db.tables import metadata

config = context.config
LOADED = (application_modules(), shared.jobs.tables, shared.records.tables, shared.access.audit)
MODE = "offline" if context.get_x_argument(as_dictionary=True).get("url") else "runtime"
OWNERSHIP = ownership(application_modules(), application().settings(MODE))


def database_url() -> str:
    return (
        context.get_x_argument(as_dictionary=True).get("url")
        or application().settings().database_url
    )


def run_on(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
        include_object=OWNERSHIP.include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    url = database_url()
    engine = create_async_engine(url, **engine_options(url, pool_size=1, wait_seconds=10))
    async with engine.connect() as connection:
        await connection.run_sync(run_on)
    await engine.dispose()


def run_offline() -> None:
    context.configure(url=database_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
