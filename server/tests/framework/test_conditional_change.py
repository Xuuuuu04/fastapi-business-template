"""
先读后写的两种写法：带条件修改没有改到任何行时报业务错误；加锁读取只能在写入事务中使用。
"""

import pytest
from sqlalchemy import delete, insert, select, update

from app.setup.build import Services
from shared.db.access import Db
from shared.errors.framework import StepRuleBroken
from tests.framework.sample_modules import SampleBusy, notes


# 条件满足时照常修改并返回行数；数据已被别人改过（条件不再满足）时抛出给定的业务错误。
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


# 只读步骤不能加锁读取，读和写必须在同一个写入事务中。
@pytest.mark.anyio
async def test_lock_needs_saving_step(sample: Services) -> None:
    async with sample.database.read() as connection:
        db = Db(connection, read_only=True, place="读取")
        with pytest.raises(StepRuleBroken):
            await db.first_for_update(select(notes))


# 插入、多行插入、修改、删除都返回真实的受影响行数。
# PostgreSQL 上插入会自动带 RETURNING，曾经返回 0、运行记录里的行数为空。
@pytest.mark.anyio
async def test_change_counts_rows_for_every_kind(sample: Services) -> None:
    async with sample.database.write() as connection:
        db = Db(connection, read_only=False, place="修改")
        assert await db.change(insert(notes).values(text="一")) == 1
        assert await db.change(insert(notes).values([{"text": "二"}, {"text": "三"}])) == 2
        assert await db.change(update(notes).values(text="改")) == 3
        assert await db.change(delete(notes).where(notes.c.text == "改")) == 3
