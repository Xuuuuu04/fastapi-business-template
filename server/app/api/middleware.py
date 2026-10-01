"""
请求中间件：为每个请求分配请求编号、限制请求正文大小和同时处理的请求数、记录一行请求日志。
响应头带上 X-Request-ID 和 X-Run-ID，出错时用这两个编号查询诊断信息。
日志只记录路由模板、状态码和耗时，不记录查询参数、请求正文和密钥。
"""

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


class RequestLimits:
    # 记录限制值和当前在途请求数；运行状态接口会读取在途数量。
    def __init__(
        self,
        max_body: int,
        max_inflight: int,
        upload_body: int = 0,
        upload_paths: tuple[str, ...] = (),
    ) -> None:
        self.max_body = max_body
        self.max_inflight = max_inflight
        self.upload_body = max(upload_body, max_body)
        self.upload_paths = upload_paths
        self.inflight = 0

    # 只有登记的上传路径使用上传大小限制，其他接口保持较小的正文限制。
    def body_limit(self, path: str) -> int:
        return self.upload_body if path.startswith(self.upload_paths) else self.max_body


class RequestMiddleware:
    # 包装下一层应用，使用共享的请求限制。
    def __init__(self, app: App, limits: RequestLimits, hsts_seconds: int = 0) -> None:
        self.app = app
        self.limits = limits
        self.hsts_seconds = hsts_seconds

    # 处理一个 HTTP 请求：分配编号、检查限制、记录日志。
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = incoming_id(scope) or secrets.token_hex(8)
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id.set(rid)
        started, status = time.perf_counter(), [500]
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
                    self.limited(receive, self.limits.body_limit(scope["path"])),
                    tagged(send, scope, rid, status, self.hsts_seconds),
                )
            except BodyTooLarge:
                status[0] = 413
                await reply(
                    send, rid, 413, "request_too_large", "请求正文超过大小限制", self.hsts_seconds
                )
            finally:
                self.limits.inflight -= 1
        finally:
            log_request(scope, status[0], started)
            request_id.reset(token)

    # 在进入业务前检查同时处理的请求数和声明的正文大小。
    def refuse(self, scope: Scope) -> tuple[int, str, str] | None:
        if self.limits.inflight >= self.limits.max_inflight:
            return 503, "too_busy", "服务繁忙，请稍后再试"
        length = header(scope, b"content-length")
        if length.isdigit() and int(length) > self.limits.body_limit(scope["path"]):
            return 413, "request_too_large", "请求正文超过大小限制"
        return None

    # 读取正文时累计大小，超过限制立即停止。
    def limited(self, receive: Receive, limit: int) -> Receive:
        total = [0]

        # 读取一段正文并检查累计大小。
        async def wrapped() -> Message:
            message = await receive()
            total[0] += len(message.get("body", b""))
            if total[0] > limit:
                raise BodyTooLarge()
            return message

        return wrapped


# 在响应头中加入请求编号和运行编号，并记下状态码。
def tagged(send: Send, scope: Scope, rid: str, status: list[int], hsts_seconds: int) -> Send:
    # 发送响应前补充响应头。
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


# 直接返回一个 JSON 错误响应，格式与统一错误响应相同。
async def reply(
    send: Send, rid: str, status: int, code: str, message: str, hsts_seconds: int = 0
) -> None:
    kind = "too_many" if status == 503 else "invalid"
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


# 给所有响应添加不缓存和浏览器安全响应头；配置 HSTS 后要求浏览器只用 HTTPS。
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


# 读取调用方传入的请求编号；格式不符时忽略，避免日志被注入内容。
def incoming_id(scope: Scope) -> str:
    value = header(scope, b"x-request-id")
    return value if VALID_ID.match(value) else ""


# 读取一个请求头。
def header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return bytes(value).decode("latin-1")
    return ""


# 记录一行请求日志：方法、路由模板、状态码、耗时和运行编号。
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
