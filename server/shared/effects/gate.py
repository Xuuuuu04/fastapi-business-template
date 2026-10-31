from typing import TYPE_CHECKING

from shared.data.models import Data
from shared.effects.service import EffectService, binding_of
from shared.effects.spec import EffectResult, ProviderSpec
from shared.errors.framework import StepRuleBroken
from shared.records.models import StepRecord

if TYPE_CHECKING:
    from shared.flow.scope import Scope


class EffectGate:
    def __init__(
        self, scope: "Scope", record: StepRecord, allowed: tuple[ProviderSpec, ...], saves: bool
    ) -> None:
        self.scope, self.record, self.allowed, self.saves = scope, record, allowed, saves

    async def call(self, spec: ProviderSpec, input: Data, *, key: str) -> EffectResult:
        service = self.require(spec)
        self.outside_transaction()
        if self.scope.checkpoint is not None:
            await self.scope.checkpoint.before_write()
        return await service.call(
            spec, input, self.scope.caller, key, self.record.remotes, self.scope.remote_writes
        )

    async def enqueue(self, spec: ProviderSpec, input: Data, *, key: str) -> str:
        from shared.effects.module import DispatchInput, dispatch
        from shared.flow.entry_errors import check_access

        service = self.require(spec)
        if not self.saves or self.scope.runtime.jobs is None:
            raise StepRuleBroken("登记外部发送任务需要声明 saves=True，并启用后台任务服务")
        check_access(dispatch, self.scope.caller)
        connection = await self.scope.tx.writer(self.scope.runtime.database, "登记外部调用")
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

    async def perform(self, id: str, *, lookup: bool = False) -> EffectResult:
        service = self.scope.runtime.effects
        if service is None:
            raise StepRuleBroken("产品没有配置外部调用服务")
        row = await service.store.read(id, self.scope.caller)
        spec = service.by_name.get(row["provider"])
        if spec is None:
            raise StepRuleBroken("外部请求的接口定义未登记")
        self.require(spec)
        self.outside_transaction()
        return await service.perform(
            id, self.scope.caller, self.record.remotes, self.scope.remote_writes, lookup=lookup
        )

    def require(self, spec: ProviderSpec) -> EffectService:
        if spec not in self.allowed or self.scope.runtime.effects is None:
            raise StepRuleBroken(f"步骤未声明或产品未配置外部调用 {spec.name}")
        self.scope.runtime.effects.adapter(spec)
        return self.scope.runtime.effects

    def outside_transaction(self) -> None:
        if self.scope.tx.connection is not None:
            raise StepRuleBroken(
                "数据库写入事务开始后不能发送或查询外部请求，请用 effects.enqueue 登记后台发送任务"
            )
