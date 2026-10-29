import sqlite3
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.setup.build import Services
from shared.db.access import Db, unique_violation
from shared.errors.framework import StepRuleBroken
from tests.framework.sample_modules import SampleBusy, notes


@pytest.mark.anyio
async def test_change_or_fail(sample: Services) -> None:
    async with sample.database.write() as connection:
        db = Db(connection, read_only=False, place="修改")
        await db.change(insert(notes).values(id=1, text="旧"))
        changed = update(notes).where(notes.c.id == 1, notes.c.text == "旧").values(text="新")
        assert await db.change_or_fail(changed, SampleBusy()) == 1
        with pytest.raises(SampleBusy):
            await db.change_or_fail(changed, SampleBusy())
        row = await db.first_for_update(select(notes).where(notes.c.id == 1))
        assert row is not None and row["text"] == "新"


@pytest.mark.anyio
async def test_lock_needs_saving_step(sample: Services) -> None:
    async with sample.database.read() as connection:
        db = Db(connection, read_only=True, place="读取")
        with pytest.raises(StepRuleBroken):
            await db.first_for_update(select(notes))


@pytest.mark.anyio
async def test_change_counts_rows_for_every_kind(sample: Services) -> None:
    async with sample.database.write() as connection:
        db = Db(connection, read_only=False, place="修改")
        assert await db.change(insert(notes).values(text="一")) == 1
        assert await db.change(insert(notes).values([{"text": "二"}, {"text": "三"}])) == 2
        assert await db.change(update(notes).values(text="改")) == 3
        assert await db.change(delete(notes).where(notes.c.text == "改")) == 3


@pytest.mark.anyio
async def test_unique_conflict_becomes_declared_error(sample: Services) -> None:
    async with sample.database.write() as connection:
        db = Db(connection, read_only=False, place="新增")
        await db.change(insert(notes).values(id=7, text="原有"), conflict=SampleBusy())
        with pytest.raises(SampleBusy):
            await db.one(
                insert(notes).values(id=7, text="重复").returning(notes), conflict=SampleBusy()
            )


@pytest.mark.parametrize(
    "orig,expected",
    [
        (sqlite3.IntegrityError("UNIQUE constraint failed: notes.id"), True),
        (SimpleNamespace(sqlstate="23505"), True),
        (sqlite3.IntegrityError("NOT NULL constraint failed: notes.text"), False),
        (SimpleNamespace(sqlstate="23503"), False),
    ],
)
def test_only_unique_violations_are_converted(orig: object, expected: bool) -> None:
    assert unique_violation(IntegrityError("INSERT", {}, cast(Any, orig))) is expected
