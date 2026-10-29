import asyncio
import json
import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders

from shared.logs.setup import request_id

log = logging.getLogger("server.request")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

VALID_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class BodyTooLarge(Exception):
    pass


class BodyTimedOut(Exception):
    pass


class RequestLimits:
    def __init__(
        self,
        max_body: int,
        max_inflight: int,
        upload_body: int = 0,
        upload_paths: tuple[str, ...] = (),
        body_seconds: float = 30,
        upload_seconds: float = 120,
    ) -> None:
        self.max_body = max_body
        self.max_inflight = max_inflight
        self.upload_body = max(upload_body, max_body)
        self.upload_paths = upload_paths
        self.body_seconds = body_seconds
        self.upload_seconds = upload_seconds
        self.inflight = 0

    def body_limit(self, path: str) -> int:
        return self.upload_body if path.startswith(self.upload_paths) else self.max_body

    def body_timeout(self, path: str) -> float:
        return self.upload_seconds if path.startswith(self.upload_paths) else self.body_seconds


class RequestMiddleware:
    def __init__(self, app: App, limits: RequestLimits, hsts_seconds: int = 0) -> None:
        self.app = app
        self.limits = limits
        self.hsts_seconds = hsts_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = incoming_id(scope) or secrets.token_hex(8)
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id.set(rid)
        started, status = time.perf_counter(), [0]
        try:
            refusal = self.refuse(scope)
            if refusal is not None:
                status[0] = refusal[0]
                await reply(send, rid, *refusal, self.hsts_seconds)
                return
            self.limits.inflight += 1
            try:
                await self.app(
                    scope,
                    self.limited(
                        receive,
                        self.limits.body_limit(scope["path"]),
                        self.limits.body_timeout(scope["path"]),
                    ),
                    tagged(send, scope, rid, status, self.hsts_seconds),
                )
            except BodyTooLarge:
                if status[0]:
                    raise
                status[0] = 413
                await reply(
                    send, rid, 413, "request_too_large", "请求正文超过大小限制", self.hsts_seconds
                )
            except BodyTimedOut:
                if status[0]:
                    raise
                status[0] = 408
                await reply(
                    send,
                    rid,
                    408,
                    "request_timeout",
                    "请求正文读取超时，请检查网络后重试",
                    self.hsts_seconds,
                )
            finally:
                self.limits.inflight -= 1
        finally:
            log_request(scope, status[0] or 500, started)
            request_id.reset(token)

    def refuse(self, scope: Scope) -> tuple[int, str, str] | None:
        if self.limits.inflight >= self.limits.max_inflight:
            return 503, "too_busy", "服务繁忙，请稍后再试"
        length = header(scope, b"content-length")
        if length.isdigit() and int(length) > self.limits.body_limit(scope["path"]):
            return 413, "request_too_large", "请求正文超过大小限制"
        return None

    def limited(self, receive: Receive, limit: int, seconds: float = 30) -> Receive:
        total = [0]
        deadline = asyncio.get_running_loop().time() + seconds
        finished = False

        async def wrapped() -> Message:
            nonlocal finished
            if finished:
                return await receive()
            try:
                async with asyncio.timeout_at(deadline):
                    message = await receive()
            except TimeoutError as error:
                raise BodyTimedOut() from error
            total[0] += len(message.get("body", b""))
            if total[0] > limit:
                raise BodyTooLarge()
            finished = message["type"] != "http.request" or not message.get("more_body", False)
            return message

        return wrapped


def tagged(send: Send, scope: Scope, rid: str, status: list[int], hsts_seconds: int) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            status[0] = message["status"]
            headers = MutableHeaders(scope=message)
            headers["X-Request-ID"] = rid
            for name, value in security_headers(hsts_seconds):
                headers[name.decode("latin-1")] = value.decode("latin-1")
            run_ids = scope.get("state", {}).get("run_ids") or []
            if run_ids and "X-Run-ID" not in headers:
                headers["X-Run-ID"] = run_ids[0]
        await send(message)

    return wrapped


async def reply(
    send: Send, rid: str, status: int, code: str, message: str, hsts_seconds: int = 0
) -> None:
    kind = "too_many" if status == 503 else "timeout" if status == 408 else "invalid"
    body: dict[str, object] = {"code": code, "kind": kind, "message": message, "request_id": rid}
    body |= {"run_id": "", "fields": []}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"x-request-id", rid.encode()),
        *security_headers(hsts_seconds),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})


def security_headers(hsts_seconds: int) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"cache-control", b"no-store"),
    ]
    if hsts_seconds:
        headers.append((b"strict-transport-security", f"max-age={hsts_seconds}".encode()))
    return headers


def incoming_id(scope: Scope) -> str:
    value = header(scope, b"x-request-id")
    return value if VALID_ID.match(value) else ""


def header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return bytes(value).decode("latin-1")
    return ""


def log_request(scope: Scope, status: int, started: float) -> None:
    route = scope.get("route")
    path = getattr(route, "path", "unmatched")
    run_ids = scope.get("state", {}).get("run_ids") or []
    log.info(
        "request method=%s route=%s status=%s ms=%.1f run_id=%s",
        scope.get("method", ""),
        path,
        status,
        (time.perf_counter() - started) * 1000,
        run_ids[0] if run_ids else "",
    )
