"""
外部接口调用服务：按外部系统建立连接池，限制并发，统一超时、重试和错误分类，并记录每次调用。
读取（GET、HEAD）和带请求编号的写入遇到暂时故障会重试；其他写入不重试，超时报告“结果待核对”。
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx2

from shared.errors.framework import (
    RemoteAuthFailed,
    RemoteNotConfigured,
    RemoteNotFound,
    RemoteRejected,
    RemoteResultUnknown,
    RemoteUnavailable,
    StepRuleBroken,
)
from shared.records.models import RemoteCallRecord
from shared.remote_calls.remote import Remote, RemoteConfig

SAFE_METHODS = ("GET", "HEAD")
RETRY_WAITS = (0.5, 2.0, 5.0)


@dataclass(frozen=True)
class RemoteReply:
    status: int
    data: Any
    text: str
    content: bytes


@dataclass(frozen=True)
class RemoteRequest:
    method: str
    path: str
    params: dict[str, Any] | None = None
    json: Any = None
    key: str = ""


class RemoteService:
    # 保存各外部系统的配置；transports 只在测试中替换网络传输。
    def __init__(
        self,
        configs: dict[str, RemoteConfig],
        transports: dict[str, httpx2.AsyncBaseTransport] | None = None,
        retry_waits: tuple[float, ...] = RETRY_WAITS,
    ) -> None:
        self.configs = configs
        self.transports = transports or {}
        self.retry_waits = retry_waits
        self.clients: dict[str, httpx2.AsyncClient] = {}
        self.limits: dict[str, asyncio.Semaphore] = {}

    # 发送一次请求并记录；按方法和请求编号决定是否重试。
    async def send(
        self, target: Remote, request: RemoteRequest, records: list[RemoteCallRecord]
    ) -> RemoteReply:
        check_path(request.path)
        record = RemoteCallRecord(target.name, request.method, request.path.split("?")[0], 0, 0.0)
        record.bytes_out = len(str(request.json or "").encode("utf-8"))
        records.append(record)
        started = time.perf_counter()
        try:
            reply = await self.attempts(target, request, record)
        except BaseException as error:
            record.error = getattr(error, "detail", type(error).__name__)
            raise
        finally:
            record.elapsed_ms = (time.perf_counter() - started) * 1000
        record.bytes_in = len(reply.content)
        return reply

    # 按重试规则反复发送，直到成功、遇到不可重试的错误或次数用完。
    async def attempts(
        self, target: Remote, request: RemoteRequest, record: RemoteCallRecord
    ) -> RemoteReply:
        retryable = request.method in SAFE_METHODS or bool(request.key)
        allowed = min(target.retries, len(self.retry_waits)) if retryable else 0
        for attempt in range(allowed + 1):
            try:
                return await self.once(target, request, record)
            except RemoteUnavailable:
                if attempt == allowed:
                    raise
                record.retries += 1
                await asyncio.sleep(self.retry_waits[attempt])
        raise RemoteUnavailable(f"外部系统 {target.name} 重试次数已用完")

    # 发送一次请求，把网络错误和状态码转成框架的错误种类。
    async def once(
        self, target: Remote, request: RemoteRequest, record: RemoteCallRecord
    ) -> RemoteReply:
        headers = {"Idempotency-Key": request.key} if request.key else {}
        async with self.limit(target):
            try:
                response = await self.client(target).request(
                    request.method,
                    request.path,
                    params=request.params,
                    json=request.json,
                    headers=headers,
                )
            except httpx2.TimeoutException as error:
                if request.method in SAFE_METHODS or request.key:
                    raise RemoteUnavailable(f"外部系统 {target.title}响应超时") from error
                raise RemoteResultUnknown(
                    f"写入外部系统 {target.title}时超时，对方可能已经处理"
                ) from error
            except httpx2.TransportError as error:
                if (
                    request.method not in SAFE_METHODS
                    and not request.key
                    and not isinstance(error, httpx2.ConnectError)
                ):
                    raise RemoteResultUnknown(
                        f"写入外部系统 {target.title}时连接中断，对方可能已经处理"
                    ) from error
                raise RemoteUnavailable(f"无法连接外部系统 {target.title}") from error
        record.status = response.status_code
        raise_for_status(target, response.status_code)
        return reply_of(response)

    # 取得外部系统的连接；没有配置时报错。
    def client(self, target: Remote) -> httpx2.AsyncClient:
        found = self.clients.get(target.name)
        if found is not None:
            return found
        config = self.configs.get(target.name)
        if config is None:
            raise RemoteNotConfigured(
                f"外部系统 {target.name}（{target.title}）没有在 APP_REMOTES 中配置"
            )
        headers = {}
        if config.token is not None:
            headers[config.token_header] = config.token_prefix + config.token.get_secret_value()
        client = httpx2.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            headers=headers,
            timeout=config.timeout or target.timeout,
            transport=self.transports.get(target.name),
        )
        self.clients[target.name] = client
        return client

    # 取得外部系统的并发上限。
    def limit(self, target: Remote) -> asyncio.Semaphore:
        return self.limits.setdefault(target.name, asyncio.Semaphore(target.concurrency))

    # 关闭全部连接。
    async def close(self) -> None:
        for client in self.clients.values():
            await client.aclose()


# 路径必须以 / 开头，不能带协议和主机，防止请求被引到配置以外的地址。
def check_path(path: str) -> None:
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        raise StepRuleBroken(f"外部接口路径 {path} 必须以 / 开头，不能包含协议和主机")


# 按状态码抛出对应的错误。
def raise_for_status(target: Remote, status: int) -> None:
    if status < 400:
        return
    if status == 429 or status >= 500:
        raise RemoteUnavailable(f"外部系统 {target.title}暂时不可用（HTTP {status}）")
    if status in (401, 403):
        raise RemoteAuthFailed(f"外部系统 {target.title}拒绝访问（HTTP {status}），请检查密钥配置")
    if status == 404:
        raise RemoteNotFound(f"外部系统 {target.title}中没有找到请求的数据")
    raise RemoteRejected(f"外部系统 {target.title}拒绝了请求（HTTP {status}）")


# 整理响应：JSON 响应解析成数据，其他响应保留文本和原始内容。
def reply_of(response: httpx2.Response) -> RemoteReply:
    data = None
    if "json" in response.headers.get("content-type", ""):
        try:
            data = response.json()
        except ValueError:
            data = None
    return RemoteReply(response.status_code, data, response.text, response.content)
