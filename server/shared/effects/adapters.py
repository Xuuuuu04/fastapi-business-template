from collections.abc import Awaitable, Callable
from dataclasses import replace

from shared.data.models import Data
from shared.effects.spec import AdapterReply
from shared.errors.framework import RemoteAuthFailed, RemoteNotFound, RemoteRejected
from shared.remote_calls.endpoint import Endpoint
from shared.remote_calls.remote import Remote
from shared.remote_calls.request import FilePart
from shared.remote_calls.serialization import request_for
from shared.remote_calls.service import RemoteService


class SdkAdapter:
    def __init__(
        self,
        send: Callable[[Data, str], Awaitable[AdapterReply]],
        lookup: Callable[[Data, str], Awaitable[AdapterReply]],
        *,
        account: str,
        simulated: bool = False,
        close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._send, self._lookup, self.simulated = send, lookup, simulated
        self._close = close
        self.identity = account

    async def send(self, input: Data, key: str) -> AdapterReply:
        return await self._send(input, key)

    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return await self._lookup(input, key)

    async def close(self) -> None:
        if self._close is not None:
            await self._close()


class HttpAdapter:
    simulated = False

    def __init__(
        self,
        service: RemoteService,
        target: Remote,
        endpoint: Endpoint,
        receipt: Callable[[int, Data], AdapterReply],
        lookup: Callable[[Data, str], Awaitable[AdapterReply]],
        files: Callable[[Data], tuple[FilePart, ...]] | None = None,
        *,
        account: str,
    ) -> None:
        self.service, self.target, self.endpoint = service, replace(target, retries=0), endpoint
        self.receipt, self._lookup = receipt, lookup
        self.files = files
        self.identity = account + "@" + service.configs[target.name].base_url + endpoint.name

    async def send(self, input: Data, key: str) -> AdapterReply:
        request = request_for(self.endpoint, input, key, self.files(input) if self.files else ())
        try:
            reply = await self.service.send(self.target, request, [])
        except (RemoteAuthFailed, RemoteNotFound, RemoteRejected):
            return AdapterReply("refused")
        return self.receipt(reply.status, reply.data)

    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return await self._lookup(input, key)

    async def close(self) -> None:
        return None
