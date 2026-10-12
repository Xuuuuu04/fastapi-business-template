"""
步骤只能发送声明过的外部效果；随业务发送通过持久任务登记，不在写事务里直接发送。
"""

from typing import TYPE_CHECKING

from shared.data.models import Data
from shared.effects.service import EffectService, binding_of
from shared.effects.spec import EffectResult, ProviderSpec
from shared.errors.framework import StepRuleBroken
from shared.records.models import StepRecord

if TYPE_CHECKING:
    from shared.flow.scope import Scope


# 步骤上下文中的外部入口，权限范围不能由业务输入扩大。
class EffectGate:
    # 绑定声明、共享事务与本步骤的记录。
    def __init__(
        self, scope: "Scope", record: StepRecord, allowed: tuple[ProviderSpec, ...], saves: bool
    ) -> None:
        self.scope, self.record, self.allowed, self.saves = scope, record, allowed, saves

    # 直接发送在业务写入之前完成，若之后保存失败，外部效果仍沿根调用记录保留。
    async def call(self, spec: ProviderSpec, input: Data, *, key: str) -> EffectResult:
        service = self.require(spec)
        self.outside_transaction()
        if self.scope.checkpoint is not None:
            await self.scope.checkpoint.before_write()
        return await service.call(
            spec, input, self.scope.caller, key, self.record.remotes, self.scope.remote_writes
        )

    # 意图与持久任务都随当前业务事务提交；回滚时不会留下发送任务。
    async def enqueue(self, spec: ProviderSpec, input: Data, *, key: str) -> str:
        from shared.effects.module import DispatchInput, dispatch
        from shared.flow.entry_errors import check_access

        service = self.require(spec)
        if not self.saves or self.scope.runtime.jobs is None:
            raise StepRuleBroken("登记外部任务需要saves=True和持久任务服务")
        check_access(dispatch, self.scope.caller)
        connection = await self.scope.tx.writer(self.scope.runtime.database, "登记外部效果")
        body = spec.input.model_validate(input).model_dump_json()
        id = await service.store.prepare(
            connection,
            spec,
            self.scope.caller,
            key,
            body,
            service.adapter(spec).simulated,
            service.now(),
            binding_of(service.adapter(spec)),
        )
        await self.scope.runtime.jobs.submit(
            connection,
            dispatch,
            DispatchInput(intent_id=id),
            self.scope.caller,
            key=id,
            request_id=self.scope.request_id,
        )
        return id

    # 持久任务只处理原意图，未知结果通过权威查询恢复。
    async def perform(self, id: str, *, lookup: bool = False) -> EffectResult:
        service = self.scope.runtime.effects
        if service is None:
            raise StepRuleBroken("没有组装外部效果服务")
        row = await service.store.read(id, self.scope.caller)
        spec = service.by_name.get(row["provider"])
        if spec is None:
            raise StepRuleBroken("外部意图协议未登记")
        self.require(spec)
        self.outside_transaction()
        return await service.perform(
            id, self.scope.caller, self.record.remotes, self.scope.remote_writes, lookup=lookup
        )

    # 组装与步骤都必须登记相同对象，不能凭同名对象冒用供应商。
    def require(self, spec: ProviderSpec) -> EffectService:
        if spec not in self.allowed or self.scope.runtime.effects is None:
            raise StepRuleBroken(f"步骤未声明或未组装外部效果 {spec.name}")
        self.scope.runtime.effects.adapter(spec)
        return self.scope.runtime.effects

    # 共享事务已开始后，即使当前步骤不是保存步骤，也不能等待外部系统。
    def outside_transaction(self) -> None:
        if self.scope.tx.connection is not None:
            raise StepRuleBroken("业务写事务开始后不能发送或查询外部效果，请登记持久任务")
