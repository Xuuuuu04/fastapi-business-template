"""
实际HTTP、SMTP和SDK适配器使用替换传输，验证受理含义与未知结果不能盲目重发。
"""

from dataclasses import replace
from pathlib import Path

import httpx2
import pytest

from shared.access.caller import SYSTEM
from shared.effects.adapters import HttpAdapter, SdkAdapter
from shared.effects.service import EffectService
from shared.effects.smtp import MailInput, MailReceipt, SmtpAdapter, SmtpConfig
from shared.effects.spec import AdapterReply
from shared.errors.framework import RemoteResultUnknown
from shared.public import Data, Endpoint, remote
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.service import RemoteService
from tests.framework.test_provider_effects import Input, Output, expire_intent, service_at

pytestmark = pytest.mark.anyio


# SMTP网络完全替换，保留真实消息构造与SMTP适配器的受理判断。
async def test_smtp_acceptance_is_not_delivery(monkeypatch) -> None:
    seen = []

    # 单收件人发送成功只表示服务器接受了消息。
    class Client:
        # 接收SSL连接参数，不连接真实网络。
        def __init__(self, *args, **kwargs):
            pass

        # 为真实适配器提供连接上下文。
        def __enter__(self):
            return self

        # 结束合成连接。
        def __exit__(self, *args):
            return None

        # 保留消息编号和信封收件人，用于验证重复键与单收件人。
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


# HTTP适配器不继承旧key即重试的行为，首次响应丢失就保存原意图待确认。
async def test_http_adapter_does_not_retry_lost_reply(tmp_path: Path) -> None:
    service, spec, _, database = await service_at(tmp_path, "http")
    count = 0

    # 上游可能已经受理后丢失HTTP回执。
    def lose_reply(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        raise httpx2.ReadTimeout("synthetic", request=request)

    target = remote("synthetic", "合成HTTP", retries=3)
    endpoint = Endpoint("synthetic.send", "POST", "/send", Input, Output, "write")
    client = RemoteService(
        {target.name: RemoteConfig(base_url="https://synthetic.invalid")},
        {target.name: httpx2.MockTransport(lose_reply)},
        retry_waits=(0,),
    )

    # 权威查询与写入分开，查询已经受理的原编号。
    async def lookup(input: Data, key: str) -> AdapterReply:
        return AdapterReply("accepted", Output(reference="vendor-1"), "vendor-1")

    adapter = HttpAdapter(
        client,
        target,
        endpoint,
        lambda status, data: AdapterReply("accepted", data),
        lookup,
        account="synthetic-http",
    )
    service = EffectService(service.store, {spec: adapter})
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.call(spec, Input(message="private-body"), SYSTEM, "stable", [], [])
        with pytest.raises(RemoteResultUnknown):
            await service.call(spec, Input(message="private-body"), SYSTEM, "stable", [], [])
        assert count == 1
    finally:
        await client.close()
        await database.close()


# 只有权威确认未执行，或协议明确安全重复，才允许未知意图再次发送。
@pytest.mark.parametrize("repeat_safe", [False, True])
async def test_unknown_recovery_requires_proof_or_safe_protocol(
    tmp_path: Path, repeat_safe: bool
) -> None:
    service, original, _, database = await service_at(tmp_path, "sdk")
    spec = replace(original, repeat_safe=repeat_safe)
    count = 0

    # 第一次连接失败不能由框架猜测是否已经执行。
    async def send(input: Data, key: str) -> AdapterReply:
        nonlocal count
        count += 1
        if count == 1:
            raise OSError("synthetic-lost-reply")
        return AdapterReply("completed", Output(reference="vendor-1"), "vendor-1")

    # 这里的明确未执行来自供应商查询，不是本地错误名称。
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
