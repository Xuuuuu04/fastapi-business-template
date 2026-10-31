from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, func, insert, select

from app.setup.build import Services
from shared.db.types import ExactNumber

pytestmark = [pytest.mark.anyio, pytest.mark.postgres_only]


async def test_amount_queries_have_numeric_semantics(services: Services) -> None:
    metadata = MetaData()
    amounts = Table(
        "amount_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", ExactNumber(18, 2)),
    )
    async with services.database.write() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.execute(
            insert(amounts), [{"amount": Decimal("10.00")}, {"amount": Decimal("2.00")}]
        )
        ordered = await connection.scalars(select(amounts.c.amount).order_by(amounts.c.amount))
        assert list(ordered) == [Decimal("2.00"), Decimal("10.00")]
        larger = await connection.scalars(
            select(amounts.c.amount).where(amounts.c.amount > Decimal("9"))
        )
        assert list(larger) == [Decimal("10.00")]
        equal = await connection.scalar(
            select(amounts.c.amount).where(amounts.c.amount == Decimal("2.0"))
        )
        assert equal == Decimal("2.00")
        assert await connection.scalar(select(func.sum(amounts.c.amount))) == Decimal("12.00")
        await connection.run_sync(metadata.drop_all)
