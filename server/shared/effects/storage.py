import hashlib
import json
import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.access.vault import Vault
from shared.db.database import Database
from shared.effects.spec import AdapterReply, ProviderSpec
from shared.effects.tables import attempts, intents
from shared.errors.framework import DuplicateRequest, NotAllowed, StepRuleBroken


def owner_of(caller: Caller) -> str:
    raw = json.dumps([caller.kind, caller.org_id, caller.id])
    return hashlib.sha256(raw.encode()).hexdigest()


class EffectStore:
    def __init__(self, database: Database, vault: Vault) -> None:
        self.database, self.vault = database, vault

    async def prepare(
        self,
        connection: AsyncConnection,
        spec: ProviderSpec,
        caller: Caller,
        key: str,
        body: str,
        simulated: bool,
        now: float,
        binding: str,
    ) -> str:
        if not key or len(key.encode()) > 512 or len(body.encode()) > 1_000_000:
            raise StepRuleBroken("外部意图需要有界稳定业务键，请求不能超过1MiB")
        owner = owner_of(caller)
        id = hashlib.sha256(json.dumps([spec.name, owner, key]).encode()).hexdigest()
        digest = hashlib.sha256(body.encode()).hexdigest()
        insert = sqlite_insert if self.database.is_sqlite else pg_insert
        await connection.execute(
            insert(intents)
            .values(
                id=id,
                provider=spec.name,
                owner=owner,
                protocol=spec.digest(),
                binding=binding,
                input_digest=digest,
                request=self.vault.encrypt(body),
                state="not_sent",
                receipt="",
                external_id="",
                simulated=simulated,
                attempt=0,
                lease_until=0,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[intents.c.id])
        )
        row = (await connection.execute(select(intents).where(intents.c.id == id))).mappings().one()
        if (row["protocol"], row["input_digest"], row["simulated"], row["binding"]) != (
            spec.digest(),
            digest,
            simulated,
            binding,
        ):
            raise DuplicateRequest("同一外部业务键的输入、协议、账号或模拟类型已经改变")
        return id

    async def read(self, id: str, caller: Caller) -> dict[str, Any]:
        async with self.database.read() as connection:
            row = (
                (await connection.execute(select(intents).where(intents.c.id == id)))
                .mappings()
                .first()
            )
        if row is None or row["owner"] != owner_of(caller):
            raise NotAllowed("外部意图不存在或不属于当前调用者")
        return dict(row)

    async def claim(self, id: str, spec: ProviderSpec, now: float, *, lookup: bool) -> int | None:
        eligible = (
            intents.c.state.in_(("unknown", "accepted"))
            if lookup
            else (
                (intents.c.state == "not_sent")
                | ((intents.c.state == "unknown") & spec.repeat_safe)
            )
        )
        values: dict[str, Any] = dict(
            attempt=intents.c.attempt + 1, lease_until=now + spec.timeout + 1, updated_at=now
        )
        if not lookup:
            values["state"] = "unknown"
        async with self.database.write() as connection:
            result = await connection.execute(
                update(intents)
                .where(
                    intents.c.id == id,
                    eligible,
                    intents.c.lease_until <= now,
                )
                .values(**values)
                .returning(intents.c.attempt)
            )
            attempt = result.scalar_one_or_none()
            if attempt is not None:
                await self.event(
                    connection, id, attempt, "lookup" if lookup else "send", "unknown", "", now
                )
        return attempt

    async def save(self, id: str, attempt: int, reply: AdapterReply, now: float) -> bool:
        body = reply.data.model_dump_json() if reply.data is not None else ""
        receipt = self.vault.encrypt(body) if body else ""
        async with self.database.write() as connection:
            await self.event(
                connection, id, attempt, "receipt", reply.state, receipt, now, reply.external_id
            )
            changed = await connection.execute(
                update(intents)
                .where(
                    intents.c.id == id,
                    intents.c.attempt == attempt,
                    intents.c.state.in_(("unknown", "accepted")),
                )
                .values(
                    state=reply.state,
                    receipt=receipt,
                    external_id=reply.external_id,
                    lease_until=0,
                    updated_at=now,
                )
            )
        return bool(changed.rowcount)

    async def event(
        self,
        connection: AsyncConnection,
        id: str,
        attempt: int,
        action: str,
        state: str,
        receipt: str,
        now: float,
        external_id: str = "",
    ) -> None:
        await connection.execute(
            attempts.insert().values(
                id=secrets.token_hex(16),
                intent_id=id,
                attempt=attempt,
                action=action,
                state=state,
                receipt=receipt,
                observed_at=now,
                external_id=external_id,
            )
        )
