from collections.abc import Awaitable, Callable
from typing import Any

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.records.models import RemoteCallRecord
from shared.remote_calls.endpoint import Endpoint, EndpointReply
from shared.remote_calls.remote import Remote
from shared.remote_calls.request import FilePart
from shared.remote_calls.serialization import request_for
from shared.remote_calls.service import RemoteReply, RemoteRequest, RemoteService, is_write


class RemoteGate:
    def __init__(
        self,
        service: RemoteService | None,
        allowed: tuple[Remote, ...],
        records: list[RemoteCallRecord],
        place: str,
        transaction_started: Callable[[], bool] | None = None,
        effects: list[RemoteCallRecord] | None = None,
        before_write: Callable[[], Awaitable[None]] | None = None,
        endpoints: tuple[Endpoint[Any, Any], ...] = (),
    ) -> None:
        self._service = service
        self._allowed = allowed
        self._records = records
        self._place = place
        self._transaction_started = transaction_started
        self._effects = effects
        self._before_write = before_write
        self._endpoints = endpoints

    async def send(self, target: Remote, request: RemoteRequest) -> RemoteReply:
        if not request.endpoint:
            raise StepRuleBroken("只能用 remote.call 调用已声明的 Endpoint")
        self.check_request(request)
        if self._transaction_started is not None and self._transaction_started():
            raise StepRuleBroken("写入事务开始后不能调用外部接口")
        if target not in self._allowed:
            raise StepRuleBroken(f"“{self._place}”访问了未声明的外部系统 {target.name}")
        if self._service is None:
            raise StepRuleBroken("没有启用外部接口服务")
        if self._before_write is not None and is_write(request):
            await self._before_write()
        return await self._service.send(target, request, self._records, self._effects)

    async def call[In: Data, Out: Data](
        self,
        target: Remote,
        endpoint: Endpoint[In, Out],
        input: In,
        *,
        key: str = "",
        files: tuple[FilePart, ...] = (),
    ) -> EndpointReply[Out]:
        if endpoint not in self._endpoints:
            raise StepRuleBroken(f"“{self._place}”调用了未声明的上游接口 {endpoint.name}")
        request = request_for(endpoint, input, key, files)
        reply = await self.send(target, request)
        return EndpointReply(reply.status, reply.data)

    def check_request(self, request: RemoteRequest) -> None:
        matched = next((e for e in self._endpoints if e.name == request.endpoint), None)
        if matched is None or request.protocol is not matched or request.input is None:
            raise StepRuleBroken(f"上游请求 {request.endpoint} 与步骤声明不一致")
        expected = request_for(matched, request.input, request.key, request.files)
        if request != expected:
            raise StepRuleBroken(f"上游请求 {request.endpoint} 与步骤声明不一致")
