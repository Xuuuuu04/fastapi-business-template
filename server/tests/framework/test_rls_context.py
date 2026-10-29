import secrets

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select, text

from app.setup.build import Services
from shared.access.caller import Caller
from shared.db.access import Db

pytestmark = [pytest.mark.anyio, pytest.mark.postgres_only]


async def test_rls_uses_configured_trusted_org(services: Services) -> None:
    role = "rls_" + secrets.token_hex(4)
    table = "rls_" + secrets.token_hex(4)
    async with services.database.write() as connection:
        await connection.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS"))
        await connection.execute(text(f"CREATE TABLE {table} (org_id text, value int)"))
        await connection.execute(text(f"INSERT INTO {table} VALUES ('alpha',1),('beta',2)"))
        await connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        await connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        await connection.execute(
            text(
                f"CREATE POLICY tenant ON {table} USING "
                "(org_id=current_setting('sample.org_id',true))"
            )
        )
        await connection.execute(text(f"GRANT SELECT ON {table} TO {role}"))
    try:
        async with services.database.write() as connection:
            await connection.execute(text(f"SET LOCAL ROLE {role}"))
            declared = Table(table, MetaData(), Column("org_id", String), Column("value", Integer))
            query = select(declared.c.value)
            for org, expected in (("alpha", [1]), ("beta", [2]), ("*", []), ("", [])):
                db = Db(
                    connection,
                    read_only=True,
                    place="RLS样例",
                    caller=Caller("tester", "user", "测试", org_id=org),
                    org_setting="sample.org_id",
                )
                assert [row["value"] for row in await db.all(query)] == expected
        async with services.database.read() as connection:
            assert not await connection.scalar(text("SELECT current_setting('sample.org_id',true)"))
    finally:
        async with services.database.write() as connection:
            await connection.execute(text(f"DROP TABLE {table}"))
            await connection.execute(text(f"DROP ROLE {role}"))
