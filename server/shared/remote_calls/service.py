"""
外部接口调用服务：按外部系统建立连接池，限制并发，统一超时、重试和错误分类，并记录每次调用。
读取（GET、HEAD）和带请求编号的写入遇到暂时故障会重试；其他写入不重试，超时报告“结果待确认”。
"""

import asyncio
import json
import time
from dataclasses import replace

import httpx2

from shared.data.limits import ResponseTooLarge, limited_bytes
from shared.errors.framework import (
    RemoteAuthFailed,
    RemoteNotConfigured,
    RemoteNotFound,
    RemoteRejected,
    RemoteResultUnknown,
    RemoteUnavailable,
    StepRuleBroken,
)
from shared.errors.kinds import BusinessError
from shared.records.models import RemoteCallRecord
from shared.remote_calls.breaker import Breaker
from shared.remote_calls.endpoint import validate_output
from shared.remote_calls.remote import Remote, RemoteConfig
from shared.remote_calls.request import RemoteReply, RemoteRequest, is_write

RETRY_WAITS = (0.5, 2.0, 5.0)


# 发送外部请求并记录结果，按请求安全性处理重试。
class RemoteService:
    # 保存各外部系统的配置；transports 只在测试中替换网络传输。
    def __init__(
        self,
        configs: dict[str, RemoteConfig],
        transports: dict[str, httpx2.AsyncBaseTransport] | None = None,
        retry_waits: tuple[float, ...] = RETRY_WAITS,
        strict_endpoints: bool = False,
    ) -> None:
        self.configs = configs
        self.strict_endpoints = strict_endpoints
        self.transports = transports or {}
        self.retry_waits = retry_waits
        self.clients: dict[str, httpx2.AsyncClient] = {}
        self.limits: dict[str, asyncio.Semaphore] = {}
        self.breakers: dict[str, Breaker] = {}

    # 发送一次请求并记录；按方法和请求编号决定是否重试。
    async def send(
        self,
        target: Remote,
        request: RemoteRequest,
        records: list[RemoteCallRecord],
        effects: list[RemoteCallRecord] | None = None,
    ) -> RemoteReply:
        check_path(request.path)
        check_accepted_statuses(request.accepted_statuses)
        record = request.record(target.name)
        records.append(record)
        if effects is not None and is_write(request):
            effects.append(record)
        started = time.perf_counter()
        breaker = self.breakers.setdefault(target.name, Breaker())
        try:
            wait = breaker.blocked()
            if wait:
                raise RemoteUnavailable(
                    f"外部系统 {target.title}连续失败，暂停调用，{wait:.0f} 秒后再试"
                )
            reply = await self.attempts(target, request, record)
            if request.protocol is not None:
                output = validate_output(request.protocol, reply.data, record)
                reply = replace(reply, data=output)
        except (RemoteUnavailable, RemoteResultUnknown) as error:
            if not wait:
                breaker.failed()
            record.error = error.detail
            raise
        except BusinessError as error:
            if is_write(request) and record.outcome == "unknown":
                breaker.failed()
                message = f"写入外部系统 {target.title}后未取得确定结果，请先查询"
                record.error = message
                raise RemoteResultUnknown(message) from error
            breaker.succeeded()
            record.error = error.detail
            raise
        except BaseException as error:
            breaker.released()
            record.error = type(error).__name__
            raise
        finally:
            record.elapsed_ms = (time.perf_counter() - started) * 1000
        breaker.succeeded()
        record.bytes_in = len(reply.content)
        return reply

    # 按重试规则反复发送，直到成功、遇到不可重试的错误或次数用完。
    async def attempts(
        self, target: Remote, request: RemoteRequest, record: RemoteCallRecord
    ) -> RemoteReply:
        retryable = not is_write(request) or bool(request.key)
        allowed = min(target.retries, len(self.retry_waits)) if retryable else 0
        for attempt in range(allowed + 1):
            try:
                return await self.once(target, request, record)
            except RemoteUnavailable:
                if attempt == allowed:
                    if is_write(request) and record.outcome == "unknown":
                        raise RemoteResultUnknown(
                            f"写入外部系统 {target.title}后未取得确定结果，请先查询"
                        ) from None
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
            client = self.client(target)
            previously_unknown = record.outcome == "unknown"
            try:
                record.outcome = "unknown"
                return await self.read_reply(
                    client, target, request, record, headers, previously_unknown
                )
            except ResponseTooLarge as error:
                if is_write(request):
                    raise RemoteResultUnknown(
                        f"外部系统 {target.title}返回内容超过上限，写入结果需要确认"
                    ) from error
                raise RemoteRejected(f"外部系统 {target.title}返回内容超过上限") from error
            except httpx2.TransportError as error:
                raise transport_problem(
                    target, request, record, previously_unknown, error
                ) from error

    # 有界读取响应，并记录哪些写入得到成功结果，哪些明确被拒绝。
    async def read_reply(
        self,
        client: httpx2.AsyncClient,
        target: Remote,
        request: RemoteRequest,
        record: RemoteCallRecord,
        headers: dict[str, str],
        previously_unknown: bool,
    ) -> RemoteReply:
        async with client.stream(
            request.method,
            request.path,
            params=request.params,
            json=request.json,
            data=request.form,
            files=[
                (part.field, (part.filename, part.content, part.content_type))
                for part in request.files
            ]
            or None,
            headers=headers,
            extensions={"endpoint": request.endpoint},
        ) as response:
            record.status = response.status_code
            if (
                not previously_unknown
                and 400 <= response.status_code < 500
                and response.status_code not in (408, 499)
            ):
                record.outcome = "failed"
            if response.status_code in request.unknown_on and is_write(request):
                record.outcome = "unknown"
                raise RemoteResultUnknown(
                    f"上游接口 {request.endpoint} 收到待确认状态 HTTP {response.status_code}"
                )
            captured = response.status_code in request.accepted_statuses
            if captured and previously_unknown and is_write(request):
                raise RemoteResultUnknown("此前写入仍未确认，捕获HTTP响应不能抹掉未知结果")
            if not captured:
                raise_for_status(target, response.status_code, request)
            maximum = self.configs[target.name].max_response_bytes
            content = await limited_bytes(response.aiter_bytes(chunk_size=65536), maximum)
            reply = reply_of(response, content)
            record.outcome = "failed" if captured else "ok"
            return reply

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


# 未连接时没有发出请求；之后的超时或中断可能已有写入，不能抹掉更早的未知结果。
def transport_problem(
    target: Remote,
    request: RemoteRequest,
    record: RemoteCallRecord,
    previously_unknown: bool,
    error: httpx2.TransportError,
) -> BusinessError:
    not_sent = isinstance(error, httpx2.ConnectError | httpx2.ConnectTimeout | httpx2.PoolTimeout)
    if not_sent and not previously_unknown:
        record.outcome = "not_sent"
    if is_write(request) and not request.key and not not_sent:
        return RemoteResultUnknown(f"写入外部系统 {target.title}时连接中断或超时，对方可能已经处理")
    return RemoteUnavailable(f"无法取得外部系统 {target.title}的响应")


# 按状态码抛出对应的错误。
def raise_for_status(target: Remote, status: int, request: RemoteRequest) -> None:
    if status < 400:
        return
    if status >= 500 or status in (408, 499):
        if is_write(request) and not request.key:
            raise RemoteResultUnknown(
                f"写入外部系统 {target.title}后收到 HTTP {status}，请先查询结果"
            )
        raise RemoteUnavailable(f"外部系统 {target.title}暂时不可用（HTTP {status}）")
    if status == 429:
        raise RemoteUnavailable(f"外部系统 {target.title}暂时不可用（HTTP {status}）")
    if status in (401, 403):
        raise RemoteAuthFailed(f"外部系统 {target.title}拒绝访问（HTTP {status}），请检查密钥配置")
    if status == 404:
        raise RemoteNotFound(f"外部系统 {target.title}中没有找到请求的数据")
    raise RemoteRejected(f"外部系统 {target.title}拒绝了请求（HTTP {status}）")


# 整理响应：JSON 响应解析成数据，其他响应保留文本和原始内容。
def reply_of(response: httpx2.Response, content: bytes) -> RemoteReply:
    data = None
    if "json" in response.headers.get("content-type", ""):
        try:
            data = json.loads(content)
        except ValueError:
            data = None
    text = content.decode(response.encoding or "utf-8", errors="replace")
    return RemoteReply(response.status_code, data, text, content)


# 只允许业务接收明确的客户端错误；超时和服务端错误继续保留写入未知保护。
def check_accepted_statuses(statuses: tuple[int, ...]) -> None:
    if any(
        type(status) is not int or not 400 <= status < 500 or status in (408, 499)
        for status in statuses
    ):
        raise StepRuleBroken("accepted_statuses 只支持除408、499外的4xx状态")
