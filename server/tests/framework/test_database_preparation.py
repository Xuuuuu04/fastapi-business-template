import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import (
    Column,
    Connection,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    event,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError

from shared.db.database import Database
from tests import testing_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def schema(monkeypatch: pytest.MonkeyPatch) -> MetaData:
    monkeypatch.delenv("APP_TEST_DATABASE_URL", raising=False)
    tables = MetaData()
    Table("parent", tables, Column("id", Integer, primary_key=True))
    Table(
        "child",
        tables,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parent.id"), nullable=False),
    )
    monkeypatch.setattr(testing_app, "metadata", tables)
    monkeypatch.setattr(testing_app, "_SNAPSHOTS", {})
    return tables


def url_at(folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{folder}/test.db"


async def test_new_paths_copy_only_empty_structure(tmp_path: Path, schema: MetaData) -> None:
    first = url_at(tmp_path / "first")
    second = url_at(tmp_path / "second")
    await testing_app.prepare_test_database(first)
    database = Database(first)
    try:
        async with database.write() as connection:
            await connection.execute(text("INSERT INTO parent VALUES (1)"))
            await connection.execute(text("CREATE TABLE extra (id INTEGER)"))
            await connection.execute(text("INSERT INTO extra VALUES (1)"))
        await testing_app.prepare_test_database(second)
        other = Database(second)
        try:
            async with other.read() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM parent")) == 0
                names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert names == ["alembic_version", "child", "parent"]
                assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    testing_app.head_revision()
                )
        finally:
            await other.close()
        async with database.read() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM parent")) == 1
    finally:
        await database.close()


async def test_existing_path_rebuilds_and_clears_committed_rows(
    tmp_path: Path, schema: MetaData
) -> None:
    url = url_at(tmp_path)
    await testing_app.prepare_test_database(url)
    database = Database(url)
    try:
        for _ in range(2):
            async with database.write() as connection:
                await connection.execute(text("INSERT INTO parent VALUES (1)"))
                await connection.execute(text("INSERT INTO child VALUES (1, 1)"))
            await testing_app.prepare_test_database(url)
            async with database.read() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM parent")) == 0
                assert await connection.scalar(text("SELECT count(*) FROM child")) == 0
    finally:
        await database.close()


async def test_snapshot_keeps_foreign_keys_on_separate_connections(
    tmp_path: Path, schema: MetaData
) -> None:
    url = url_at(tmp_path)
    await testing_app.prepare_test_database(url)
    first, second = Database(url), Database(url)
    try:
        async with first.write() as connection:
            await connection.execute(text("INSERT INTO parent VALUES (1)"))
        async with second.write() as connection:
            await connection.execute(text("INSERT INTO child VALUES (1, 1)"))
        for database in (first, second):
            with pytest.raises(IntegrityError):
                async with database.write() as connection:
                    await connection.execute(text("INSERT INTO child VALUES (2, 999)"))
            with pytest.raises(IntegrityError):
                async with database.write() as connection:
                    await connection.execute(text("DELETE FROM parent WHERE id = 1"))
    finally:
        await first.close()
        await second.close()


async def test_table_column_index_and_revision_changes_make_new_snapshots(
    tmp_path: Path, schema: MetaData, monkeypatch: pytest.MonkeyPatch
) -> None:
    await testing_app.prepare_test_database(url_at(tmp_path / "initial"))
    original_keys = set(testing_app._SNAPSHOTS)
    extra = Table("extra", schema, Column("id", Integer, primary_key=True))
    await testing_app.prepare_test_database(url_at(tmp_path / "table"))
    extra.append_column(Column("value", Integer, index=True, server_default="7"))
    changed = url_at(tmp_path / "column")
    await testing_app.prepare_test_database(changed)
    monkeypatch.setattr(testing_app, "head_revision", lambda: "different-head")
    revised = url_at(tmp_path / "revision")
    await testing_app.prepare_test_database(revised)
    assert len(set(testing_app._SNAPSHOTS) - original_keys) == 3
    database = Database(revised)
    try:
        async with database.write() as connection:
            await connection.execute(text("INSERT INTO extra (id) VALUES (1)"))
            assert await connection.scalar(text("SELECT value FROM extra")) == 7
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "different-head"
            )
            indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes("extra"))
            assert indexes[0]["column_names"] == ["value"]
    finally:
        await database.close()


async def test_warm_snapshot_avoids_ddl_but_explicit_reset_still_rebuilds(
    tmp_path: Path, schema: MetaData, monkeypatch: pytest.MonkeyPatch
) -> None:
    await testing_app.prepare_test_database(url_at(tmp_path / "warm"))
    calls = []
    original = schema.create_all

    def tracked(*args: Any, **kwargs: Any) -> None:
        calls.append(True)
        original(*args, **kwargs)

    monkeypatch.setattr(schema, "create_all", tracked)
    url = url_at(tmp_path / "copy")
    await testing_app.prepare_test_database(url)
    assert calls == []
    await testing_app.reset_database(url)
    assert calls == [True]


async def test_explicit_database_address_uses_full_reset(
    tmp_path: Path, schema: MetaData, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = url_at(tmp_path)
    monkeypatch.setenv("APP_TEST_DATABASE_URL", url)
    await testing_app.prepare_test_database(url)
    assert testing_app._SNAPSHOTS == {}


async def test_custom_create_hooks_do_not_reuse_snapshots(tmp_path: Path, schema: MetaData) -> None:
    calls: list[str] = []

    def seed(target: Table, connection: Connection, **kwargs: object) -> None:
        calls.append(str(connection.engine.url))
        connection.execute(text("INSERT INTO parent VALUES (:id)"), {"id": len(calls)})

    event.listen(schema.tables["parent"], "after_create", seed)
    for expected in (1, 2):
        url = url_at(tmp_path / str(expected))
        await testing_app.prepare_test_database(url)
        database = Database(url)
        try:
            async with database.read() as connection:
                assert await connection.scalar(text("SELECT id FROM parent")) == expected
        finally:
            await database.close()
    assert len(calls) == 2 and testing_app._SNAPSHOTS == {}


async def test_concurrent_new_paths_do_not_share_connections_or_data(
    tmp_path: Path, schema: MetaData
) -> None:
    urls = [url_at(tmp_path / str(index)) for index in range(4)]
    await asyncio.gather(*(testing_app.prepare_test_database(url) for url in urls))
    assert len(testing_app._SNAPSHOTS) == 1
    for url in urls:
        database = Database(url)
        try:
            async with database.write() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM parent")) == 0
                await connection.execute(text("INSERT INTO parent VALUES (1)"))
        finally:
            await database.close()


async def test_concurrent_sqlite_open_write_and_write_serialize(
    tmp_path: Path, schema: MetaData
) -> None:
    url = url_at(tmp_path / "concurrent")
    await testing_app.prepare_test_database(url)
    database = Database(url)
    try:

        async def insert_with_write(row_id: int) -> None:
            async with database.write() as connection:
                await connection.execute(text("INSERT INTO parent VALUES (:id)"), {"id": row_id})

        async def insert_with_open_write(row_id: int) -> None:
            connection = await database.open_write()
            try:
                await connection.scalar(text("SELECT count(*) FROM parent"))
                await connection.execute(text("INSERT INTO parent VALUES (:id)"), {"id": row_id})
                await connection.commit()
            finally:
                await connection.close()

        await asyncio.gather(
            *(
                insert_with_open_write(i) if i % 2 == 0 else insert_with_write(i)
                for i in range(1, 21)
            )
        )
        async with database.read() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM parent")) == 20
    finally:
        await database.close()
