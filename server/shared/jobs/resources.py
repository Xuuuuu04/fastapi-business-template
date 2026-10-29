import hashlib
import secrets

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import StepRuleBroken
from shared.jobs.limits import ResourceLimit
from shared.jobs.resource_tables import leases, pools


class ResourceWait(Exception):
    def __init__(self, until: float) -> None:
        self.until = until


async def acquire(
    connection: AsyncConnection,
    resources: tuple[ResourceLimit, ...],
    owner: str,
    attempt: int,
    now: float,
    until: float,
) -> float | None:
    if not resources:
        return None
    try:
        async with connection.begin_nested():
            for resource in sorted(resources, key=lambda item: item.name):
                await acquire_one(connection, resource, owner, attempt, now, until)
    except ResourceWait as error:
        return error.until
    return None


async def acquire_one(
    connection: AsyncConnection,
    resource: ResourceLimit,
    owner: str,
    attempt: int,
    now: float,
    until: float,
) -> None:
    id = await register_pool(connection, resource)
    row = (
        (await connection.execute(select(pools).where(pools.c.id == id).with_for_update()))
        .mappings()
        .one()
    )
    if row["capacity"] != resource.concurrency:
        raise StepRuleBroken("资源并发声明与已登记额度不同，请停止旧worker并明确调整额度")
    if row["cooldown_until"] > now:
        raise ResourceWait(row["cooldown_until"])
    await connection.execute(
        delete(leases).where(leases.c.pool_id == id, leases.c.lease_until <= now)
    )
    active = leases.c.pool_id == id, leases.c.lease_until > now
    count = await connection.scalar(select(func.count()).select_from(leases).where(*active))
    if (count or 0) >= resource.concurrency:
        deadline = await connection.scalar(select(func.min(leases.c.lease_until)).where(*active))
        raise ResourceWait(float(deadline or now + 0.1))
    await connection.execute(
        leases.insert().values(
            id=secrets.token_hex(16),
            pool_id=id,
            owner=owner,
            attempt=attempt,
            lease_until=until,
            cooldown=resource.cooldown,
        )
    )


async def release(connection: AsyncConnection, owner: str, attempt: int, now: float) -> None:
    where = leases.c.owner == owner, leases.c.attempt == attempt
    rows = (await connection.execute(select(leases).where(*where))).mappings().all()
    for row in sorted(rows, key=lambda item: item["pool_id"]):
        until = now + row["cooldown"]
        await connection.execute(
            update(pools)
            .where(pools.c.id == row["pool_id"])
            .values(
                cooldown_until=case(
                    (pools.c.cooldown_until < until, until), else_=pools.c.cooldown_until
                )
            )
        )
    await connection.execute(delete(leases).where(*where))


async def extend(connection: AsyncConnection, owner: str, attempt: int, until: float) -> None:
    await connection.execute(
        update(leases)
        .where(leases.c.owner == owner, leases.c.attempt == attempt)
        .values(lease_until=until)
    )


async def cool(connection: AsyncConnection, name: str, until: float) -> None:
    id = hashlib.sha256(name.encode()).hexdigest()
    await connection.execute(
        update(pools)
        .where(pools.c.id == id)
        .values(
            cooldown_until=case(
                (pools.c.cooldown_until < until, until), else_=pools.c.cooldown_until
            )
        )
    )


async def register_pool(connection: AsyncConnection, resource: ResourceLimit) -> str:
    id = hashlib.sha256(resource.name.encode()).hexdigest()
    insert = sqlite_insert if connection.dialect.name == "sqlite" else pg_insert
    await connection.execute(
        insert(pools)
        .values(
            id=id,
            name=resource.name[:100],
            capacity=resource.concurrency,
            cooldown_until=0,
            next_position=0,
        )
        .on_conflict_do_nothing(index_elements=[pools.c.id])
    )
    return id


async def serial_position(connection: AsyncConnection, key: str) -> int:
    id = await register_pool(connection, ResourceLimit("serial." + key))
    result = await connection.execute(
        update(pools)
        .where(pools.c.id == id)
        .values(next_position=pools.c.next_position + 1)
        .returning(pools.c.next_position)
    )
    return int(result.scalar_one())


async def reconfigure(connection: AsyncConnection, resource: ResourceLimit, now: float) -> None:
    if resource.concurrency < 1 or resource.name.startswith("serial."):
        raise StepRuleBroken("只允许调整明确资源的正整数额度，串行键不改为并行")
    id = await register_pool(connection, resource)
    await connection.execute(select(pools.c.id).where(pools.c.id == id).with_for_update())
    count = await connection.scalar(
        select(func.count())
        .select_from(leases)
        .where(leases.c.pool_id == id, leases.c.lease_until > now)
    )
    if count:
        raise StepRuleBroken("资源仍有在途尝试，请先停止领取并等待尝试结束")
    await connection.execute(
        update(pools).where(pools.c.id == id).values(capacity=resource.concurrency)
    )
