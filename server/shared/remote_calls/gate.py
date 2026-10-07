"""
模块拿到的 remote 参数 RemoteGate：只能访问声明过的外部系统。
步骤通过 @step(remotes=[...]) 声明；存储实现可以访问模块 module.py 中声明的全部外部系统。
"""

from collections.abc import Callable
from typing import Any

from shared.errors.framework import StepRuleBroken
from shared.records.models import RemoteCallRecord
from shared.remote_calls.remote import Remote
from shared.remote_calls.service import RemoteReply, RemoteRequest, RemoteService


# 步骤使用的外部接口入口，只允许访问已声明的外部系统。
class RemoteGate:
    # 绑定调用服务、允许访问的外部系统和本步骤的调用记录。
    def __init__(
        self,
        service: RemoteService | None,
        allowed: tuple[Remote, ...],
        records: list[RemoteCallRecord],
        place: str,
        transaction_started: Callable[[], bool] | None = None,
        effects: list[RemoteCallRecord] | None = None,
    ) -> None:
        self._service = service
        self._allowed = allowed
        self._records = records
        self._place = place
        self._transaction_started = transaction_started
        self._effects = effects

    # 读取数据；遇到暂时故障自动重试。
    async def get(
        self, target: Remote, path: str, *, params: dict[str, Any] | None = None
    ) -> RemoteReply:
        return await self.send(target, RemoteRequest("GET", path, params=params))

    # 提交数据；带 key 时对方可以按请求编号去重，才会在暂时故障时重试。
    async def post(
        self, target: Remote, path: str, *, json: Any = None, key: str = ""
    ) -> RemoteReply:
        return await self.send(target, RemoteRequest("POST", path, json=json, key=key))

    # 修改数据；规则与 post 相同。
    async def put(
        self, target: Remote, path: str, *, json: Any = None, key: str = ""
    ) -> RemoteReply:
        return await self.send(target, RemoteRequest("PUT", path, json=json, key=key))

    # 删除数据；规则与 post 相同。
    async def delete(self, target: Remote, path: str, *, key: str = "") -> RemoteReply:
        return await self.send(target, RemoteRequest("DELETE", path, key=key))

    # 检查外部系统已声明后发送请求。
    async def send(self, target: Remote, request: RemoteRequest) -> RemoteReply:
        if self._transaction_started is not None and self._transaction_started():
            raise StepRuleBroken("写入事务开始后不能调用外部接口")
        if target not in self._allowed:
            raise StepRuleBroken(f"“{self._place}”访问了未声明的外部系统 {target.name}")
        if self._service is None:
            raise StepRuleBroken("没有启用外部接口服务")
        return await self._service.send(target, request, self._records, self._effects)
