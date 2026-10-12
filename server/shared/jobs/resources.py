"""
短事务原子取得多个资源，租期与业务尝试一同延长，延后或重试时释放执行位置。
"""

import hashlib
import secrets

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.errors.framework import StepRuleBroken
from shared.jobs.limits import ResourceLimit
from shared.jobs.resource_tables import leases, pools


# 拒绝领取只携带下一次检查时间，不让调用方在事务里睡眠。
class ResourceWait(Exception):
    # 等待结束点来自资源的实际冷却或在途租期。
    def __init__(self, until: float) -> None:
        self.until = until


# 多资源按固定顺序加锁，失败回滚本次所有领取，避免只拿到一部分资源。
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


# 资源行锁串行维护额度；SQLite短写事务使用IMMEDIATE避免读后升级写锁失败。
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


# 完成或等待重试都归还位置；没有效果的领取失败不会调用这条冷却路径。
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


# 心跳只延长当前尝试的位置，不能替旧尝试重新取得额度。
async def extend(connection: AsyncConnection, owner: str, attempt: int, until: float) -> None:
    await connection.execute(
        update(leases)
        .where(leases.c.owner == owner, leases.c.attempt == attempt)
        .values(lease_until=until)
    )


# 主动冷却可由明确429等回执触发，不能缩短已经存在的冷却。
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


# 行登记先取得写入锁，避免两个worker同时创建额度。
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


# 同一时刻提交也保留真实登记顺序，不用随机任务编号决定业务先后。
async def serial_position(connection: AsyncConnection, key: str) -> int:
    id = await register_pool(connection, ResourceLimit("serial." + key))
    result = await connection.execute(
        update(pools)
        .where(pools.c.id == id)
        .values(next_position=pools.c.next_position + 1)
        .returning(pools.c.next_position)
    )
    return int(result.scalar_one())
