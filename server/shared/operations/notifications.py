"""
通用提醒通道与Webhook，发送语义为至少一次；不把失败当已通知。
"""

import json
import secrets
import time
from typing import Any, Protocol

import httpx2
from sqlalchemy import insert, select, update

from shared.db.access import Db
from shared.operations.config import OperationsConfig
from shared.pipelines.tables import notifications


# 新通道可实现相同接口，不向业务代码写死平台。
class Channel(Protocol):
    # 通道接收平台无关提醒正文。
    async def send(self, payload: dict[str, Any]) -> None: ...


# 通用JSON和两种机器人文本包装共用传输与预算。
class Webhook:
    # 目标保存在SecretStr，不进入运行记录。
    def __init__(self, config: OperationsConfig) -> None:
        self.config = config

    # 有界发送并检查平台回执，避免HTTP200却未通知。
    async def send(self, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False)
        body: dict[str, Any] = payload
        if self.config.webhook_format == "wecom":
            body = {"msgtype": "text", "text": {"content": content}}
        elif self.config.webhook_format == "feishu":
            body = {"msg_type": "text", "content": {"text": content}}
        url = self.config.webhook_url
        if url is None:
            raise ValueError("没有提醒目标")
        async with (
            httpx2.AsyncClient(
                timeout=self.config.webhook_timeout, follow_redirects=False
            ) as client,
            client.stream("POST", url.get_secret_value(), json=body) as response,
        ):
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise ValueError("Webhook响应超出预算")
        if raw:
            reply = json.loads(raw)
            if reply.get("errcode", reply.get("code", 0)) != 0:
                raise ValueError("Webhook平台拒绝提醒")


# 唯一键去重；调用者事务保证记录与本次运维事实一起保存。
async def enqueue(db: Db, kind: str, key: str, payload: dict[str, Any], org: str = "*") -> None:
    exists = await db.first(
        select(notifications.c.id).where(notifications.c.kind == kind, notifications.c.key == key)
    )
    if exists:
        return
    await db.change(
        insert(notifications).values(
            id=secrets.token_hex(16),
            org_id=org,
            kind=kind,
            key=key,
            payload_json=json.dumps(payload, ensure_ascii=False),
            state="pending",
            created_at=time.time(),
            attempt=0,
            error="",
        )
    )


# 每次一条、锁单条通知，不长期锁业务表；失败仍pending并记录次数，不保存目标URL。
async def deliver(db: Db, channel: Channel) -> int:
    row = await db.first(
        select(notifications)
        .where(notifications.c.state == "pending")
        .order_by(notifications.c.attempt, notifications.c.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return 0
    values: dict[str, Any] = {"attempt": row["attempt"] + 1}
    try:
        await channel.send(
            dict(
                id=row["id"],
                kind=row["kind"],
                key=row["key"],
                org_id=row["org_id"],
                details=json.loads(row["payload_json"]),
            )
        )
        values.update(state="sent", sent_at=time.time(), error="")
    except (httpx2.HTTPError, ValueError, OSError) as error:
        values["error"] = type(error).__name__
    await db.change(update(notifications).where(notifications.c.id == row["id"]).values(**values))
    return 1
