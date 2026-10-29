from dataclasses import replace
from pathlib import Path

import pytest

from shared.access.caller import SYSTEM
from shared.effects.adapters import SdkAdapter
from shared.effects.service import EffectService
from shared.effects.smtp import MailInput, MailReceipt, SmtpAdapter, SmtpConfig
from shared.effects.spec import AdapterReply
from shared.errors.framework import RemoteResultUnknown
from shared.public import Data
from tests.framework.test_provider_effects import Input, Output, expire_intent, service_at

pytestmark = pytest.mark.anyio


async def test_smtp_acceptance_is_not_delivery(monkeypatch) -> None:
    seen = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def send_message(self, message, sender, recipients):
            seen.append((str(message["Message-ID"]), recipients))
            return {}

    monkeypatch.setattr("shared.effects.smtp.smtplib.SMTP_SSL", Client)
    adapter = SmtpAdapter(SmtpConfig(host="synthetic.invalid", account="synthetic-mail"))
    request = MailInput(
        sender="sender@example.invalid",
        recipient="reader@example.invalid",
        subject="合成消息",
        text="synthetic-body",
    )
    result = await adapter.send(request, "stable-intent")
    assert result.state == "accepted" and isinstance(result.data, MailReceipt)
    assert not adapter.simulated and seen == [
        ("<stable-intent@fastapi.local>", [request.recipient])
    ]
    assert (await adapter.lookup(request, "stable-intent")).state == "unknown"


@pytest.mark.parametrize("repeat_safe", [False, True])
async def test_unknown_recovery_requires_proof_or_safe_protocol(
    tmp_path: Path, repeat_safe: bool
) -> None:
    service, original, _, database = await service_at(tmp_path, "sdk")
    spec = replace(original, repeat_safe=repeat_safe)
    count = 0

    async def send(input: Data, key: str) -> AdapterReply:
        nonlocal count
        count += 1
        if count == 1:
            raise OSError("synthetic-lost-reply")
        return AdapterReply("completed", Output(reference="vendor-1"), "vendor-1")

    async def lookup(input: Data, key: str) -> AdapterReply:
        return AdapterReply("not_sent", Output(reference="confirmed-absent"))

    service = EffectService(
        service.store, {spec: SdkAdapter(send, lookup, account="synthetic-sdk")}
    )
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.call(spec, Input(message="body"), SYSTEM, "stable", [], [])
        async with database.read() as connection:
            from sqlalchemy import select

            from shared.effects.tables import intents

            id = (await connection.execute(select(intents.c.id))).scalar_one()
        await expire_intent(database, id)
        if not repeat_safe:
            with pytest.raises(RemoteResultUnknown):
                await service.call(spec, Input(message="body"), SYSTEM, "stable", [], [])
            result = await service.perform(id, SYSTEM, [], [], lookup=True)
            assert result.state == "not_sent"
        result = await service.call(spec, Input(message="body"), SYSTEM, "stable", [], [])
        again = await service.perform(id, SYSTEM, [], [], lookup=True)
        assert result.state == again.state == "completed" and count == 2
    finally:
        await database.close()
