from collections.abc import Awaitable, Callable

from shared.data.models import Data
from shared.effects.spec import AdapterReply


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
