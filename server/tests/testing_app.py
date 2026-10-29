import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import dialect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateIndex, CreateTable

import shared.access.audit
import shared.jobs.tables
import shared.records.tables
from app.setup.application import application
from app.setup.catalog import MODULES
from shared.access.keys import ApiKeyConfig, hash_key
from shared.config.settings import Settings
from shared.db.schema import head_revision
from shared.db.tables import metadata

LOADED = (MODULES, shared.jobs.tables, shared.records.tables, shared.access.audit)

KEY = {"X-API-Key": "test-full-key"}
READER = {"X-API-Key": "test-reader-key"}

KEYS = [
    ApiKeyConfig(
        name="tester", key_sha256=hash_key("test-full-key"), permissions=["*"], org_id="*"
    ),
    ApiKeyConfig(
        name="reader",
        key_sha256=hash_key("test-reader-key"),
        permissions=["sample_calc.read"],
    ),
]

_SNAPSHOT_FOLDER = tempfile.TemporaryDirectory(prefix="test-database-schema-")
_SNAPSHOTS: dict[str, Path] = {}


def database_url(folder: Path) -> str:
    return os.environ.get("APP_TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{folder}/test.db"


def on_postgres() -> bool:
    return os.environ.get("APP_TEST_DATABASE_URL", "").startswith("postgresql")


def make_settings(folder: Path, **changes: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "test",
        "database_url": database_url(folder),
        "api_keys": KEYS,
        "file_root": str(folder / "files"),
        "upload_root": str(folder / "uploads"),
        "docs": True,
        "step_checks": True,
    }
    values.update(changes)
    return application().settings("test", **values)


async def reset_database(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
            await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            await connection.run_sync(metadata.create_all)
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            )
            await connection.execute(
                text("INSERT INTO alembic_version VALUES (:head)"), {"head": head_revision()}
            )
    finally:
        await engine.dispose()


def _schema_key() -> str:
    sqlite = dialect()
    statements = [head_revision()]
    for table in metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=sqlite)))
        statements.extend(
            sorted(str(CreateIndex(index).compile(dialect=sqlite)) for index in table.indexes)
        )
    return hashlib.sha256("\n".join(statements).encode()).hexdigest()


def _has_create_hooks() -> bool:
    targets = [metadata, *metadata.sorted_tables]
    table_hooks = any(
        target.dispatch.before_create or target.dispatch.after_create for target in targets
    )
    index_hooks = any(
        index.dispatch.before_create or index.dispatch.after_create
        for table in metadata.sorted_tables
        for index in table.indexes
    )
    return table_hooks or index_hooks


async def prepare_test_database(url: str) -> None:
    from tests.postgres_setup import prepare, reusable

    if reusable(url, _has_create_hooks()):
        await prepare(url, _schema_key(), reset_database)
        return
    parsed = make_url(url)
    path = Path(parsed.database) if parsed.database else None
    if (
        os.environ.get("APP_TEST_DATABASE_URL")
        or parsed.drivername != "sqlite+aiosqlite"
        or parsed.query
        or path is None
        or parsed.database == ":memory:"
        or path.name != "test.db"
        or path.exists()
        or Path(f"{path}-wal").exists()
        or Path(f"{path}-shm").exists()
        or _has_create_hooks()
    ):
        await reset_database(url)
        return
    key = _schema_key()
    snapshot = _SNAPSHOTS.get(key)
    if snapshot is None:
        descriptor, name = tempfile.mkstemp(suffix=".db", dir=_SNAPSHOT_FOLDER.name)
        os.close(descriptor)
        candidate = Path(name)
        try:
            await reset_database(f"sqlite+aiosqlite:///{candidate}")
            snapshot = _SNAPSHOTS.setdefault(key, candidate)
        finally:
            if _SNAPSHOTS.get(key) != candidate:
                candidate.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(snapshot, path)


def prepare_test_database_now(url: str) -> None:
    asyncio.run(prepare_test_database(url))


def reset_database_now(url: str) -> None:
    asyncio.run(reset_database(url))
