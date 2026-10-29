import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from shared.access.caller import SYSTEM, Caller
from shared.access.vault import Vault
from shared.db.database import Database
from shared.effects.service import EffectService
from shared.effects.spec import AdapterReply, ProviderSpec
from shared.effects.storage import EffectStore
from shared.effects.tables import intents
from shared.errors.framework import DuplicateRequest, NotAllowed, RemoteResultUnknown
from shared.public import Data, meaning
from tests.testing_app import make_settings, reset_database

pytestmark = pytest.mark.anyio


class Input(Data):
    message: str = meaning("合成消息")


class Output(Data):
    reference: str = meaning("合成供应商编号")


class Adapter:
    simulated = True
    identity = "synthetic-account"

    def __init__(self) -> None:
        self.sent = 0
        self.lookup_reply = AdapterReply("completed", Output(reference="vendor-1"), "vendor-1")
        self.wait: asyncio.Event | None = None
        self.started = asyncio.Event()

    async def send(self, input: Data, key: str) -> AdapterReply:
        self.sent += 1
        self.started.set()
        if self.wait is not None:
            await self.wait.wait()
        return AdapterReply("accepted", Output(reference="vendor-1"), "vendor-1")

    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return self.lookup_reply

    async def close(self) -> None:
        return None


async def service_at(tmp_path: Path, transport="smtp"):
    settings = make_settings(tmp_path)
    await reset_database(settings.database_url)
    database = Database(settings.database_url)
    spec = ProviderSpec("messages.send", "合成外部消息", Input, Output, transport)
    adapter = Adapter()
    store = EffectStore(database, Vault(["synthetic-encryption-key"]))
    return EffectService(store, {spec: adapter}), spec, adapter, database


@pytest.mark.parametrize("transport", ["http", "smtp", "sdk"])
async def test_repeat_submission_and_encrypted_request(tmp_path: Path, transport: str) -> None:
    service, spec, adapter, database = await service_at(tmp_path, transport)
    try:
        result = await service.call(spec, Input(message="private-body"), SYSTEM, "one", [], [])
        again = await service.call(spec, Input(message="private-body"), SYSTEM, "one", [], [])
        assert result == again and adapter.sent == 1 and result.state == "accepted"
        assert result.simulated and result.data.reference == "vendor-1"
        async with database.read() as connection:
            row = (await connection.execute(select(intents))).mappings().one()
        assert "private-body" not in row["request"] and "vendor-1" not in row["receipt"]
        with pytest.raises(DuplicateRequest):
            await service.call(spec, Input(message="changed"), SYSTEM, "one", [], [])
        adapter.simulated = False
        with pytest.raises(DuplicateRequest):
            await service.call(spec, Input(message="private-body"), SYSTEM, "one", [], [])
    finally:
        await database.close()


async def test_receipt_commit_failure_survives_restart(tmp_path: Path, monkeypatch) -> None:
    service, spec, adapter, database = await service_at(tmp_path)
    original = service.store.save

    async def fail_save(*args, **kwargs) -> bool:
        raise OSError("合成本地保存失败")

    monkeypatch.setattr(service.store, "save", fail_save)
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.call(spec, Input(message="mail"), SYSTEM, "one", [], [])
        monkeypatch.setattr(service.store, "save", original)
        restarted = EffectService(service.store, {spec: adapter})
        with pytest.raises(RemoteResultUnknown):
            await restarted.call(spec, Input(message="mail"), SYSTEM, "one", [], [])
        async with database.read() as connection:
            id = (await connection.execute(select(intents.c.id))).scalar_one()
        result = await restarted.perform(id, SYSTEM, [], [], lookup=True)
        assert result.state == "unknown"
        await expire_intent(database, id)
        result = await restarted.perform(id, SYSTEM, [], [], lookup=True)
        assert result.state == "completed" and adapter.sent == 1
    finally:
        await database.close()


async def test_cancel_and_concurrent_repeat_stay_unknown(tmp_path: Path) -> None:
    service, spec, adapter, database = await service_at(tmp_path)
    adapter.wait = asyncio.Event()
    records, effects = [], []
    task = asyncio.create_task(
        service.call(spec, Input(message="mail"), SYSTEM, "one", records, effects)
    )
    try:
        await adapter.started.wait()
        with pytest.raises(RemoteResultUnknown):
            await service.call(spec, Input(message="mail"), SYSTEM, "one", [], [])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert effects[0].outcome == "unknown" and adapter.sent == 1
        async with database.read() as connection:
            row = (await connection.execute(select(intents))).mappings().one()
        assert row["state"] == "unknown"
        with pytest.raises(NotAllowed):
            await service.perform(row["id"], Caller("other", "user", "其他人"), [], [])
    finally:
        task.cancel()
        await database.close()


async def expire_intent(database: Database, id: str) -> None:
    async with database.write() as connection:
        await connection.execute(intents.update().where(intents.c.id == id).values(lease_until=0))
