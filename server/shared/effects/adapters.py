"""
HTTP沿用连接池和上游协议，SDK通过明确函数接入；两者不自行重试未知写入。
"""

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


# 供应商SDK只负责一次调用和权威查询，重复策略集中在EffectService。
class SdkAdapter:
    # 产品工厂注入已配置客户端的方法，秘密不进入公开声明。
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

    # 只执行一次业务调用，不因为SDK错误自动发送第二次。
    async def send(self, input: Data, key: str) -> AdapterReply:
        return await self._send(input, key)

    # 查证原业务编号，不能用新编号试发来推定原请求没有执行。
    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return await self._lookup(input, key)

    # 产品显式提供SDK资源的关闭入口，框架不猜测SDK内部客户端字段。
    async def close(self) -> None:
        if self._close is not None:
            await self._close()


# HTTP适配器仍由统一RemoteService处理限流、连接和字段验证。
class HttpAdapter:
    simulated = False

    # 成功含义由供应商回执解释，不能统一把HTTP200解释为业务完成。
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

    # 写入只发一次，稳定编号仍传给供应商，但编号本身不授予自动重试权限。
    async def send(self, input: Data, key: str) -> AdapterReply:
        request = request_for(self.endpoint, input, key, self.files(input) if self.files else ())
        try:
            reply = await self.service.send(self.target, request, [])
        except (RemoteAuthFailed, RemoteNotFound, RemoteRejected):
            return AdapterReply("refused")
        return self.receipt(reply.status, reply.data)

    # 查询使用产品声明的供应商查询协议，不推定HTTP404必然表示未执行。
    async def lookup(self, input: Data, key: str) -> AdapterReply:
        return await self._lookup(input, key)

    # HTTP连接池由应用的RemoteService统一关闭，不重复拥有连接资源。
    async def close(self) -> None:
        return None
