import asyncio
import hashlib
from typing import Any

from shared.access.caller import Caller
from shared.data.models import Data
from shared.effects.spec import AdapterReply, EffectAdapter, EffectResult, ProviderSpec
from shared.effects.storage import EffectStore
from shared.errors.framework import RemoteRejected, RemoteResultUnknown, StepRuleBroken
from shared.records.models import RemoteCallRecord
from shared.timing.clock import Clock, RealClock
from shared.timing.current import clocked, monotonic
from shared.timing.current import now as business_now


class EffectService:
    def __init__(self, store: EffectStore, bindings: dict[ProviderSpec, EffectAdapter]) -> None:
        self.clock: Clock = RealClock()

        self.store, self.bindings = store, bindings
        self.by_name = {spec.name: spec for spec in bindings}
        if len(self.by_name) != len(bindings):
            raise StepRuleBroken("供应商效果名称重复")
        for spec, adapter in bindings.items():
            spec.validate()
            binding_of(adapter)
            configure = getattr(adapter, "configure_limit", None)
            if configure is not None:
                configure(spec.concurrency)
        self.limits = {spec: asyncio.Semaphore(spec.concurrency) for spec in bindings}

    def now(self) -> float:
        return self.clock.now()

    @clocked
    async def close(self) -> None:
        seen = set()
        for adapter in self.bindings.values():
            if id(adapter) not in seen:
                seen.add(id(adapter))
                await adapter.close()

    @clocked
    async def call(
        self,
        spec: ProviderSpec,
        input: Data,
        caller: Caller,
        key: str,
        records: list[RemoteCallRecord],
        effects: list[RemoteCallRecord],
    ) -> EffectResult:
        adapter = self.adapter(spec)
        body = spec.input.model_validate(input).model_dump_json()
        async with self.store.database.write() as connection:
            id = await self.store.prepare(
                connection,
                spec,
                caller,
                key,
                body,
                adapter.simulated,
                business_now(),
                binding_of(adapter),
            )
        return await self.perform(id, caller, records, effects)

    @clocked
    async def perform(
        self,
        id: str,
        caller: Caller,
        records: list[RemoteCallRecord],
        effects: list[RemoteCallRecord],
        *,
        lookup: bool = False,
    ) -> EffectResult:
        row = await self.store.read(id, caller)
        spec = self.by_name.get(row["provider"])
        if spec is None or spec.digest() != row["protocol"]:
            raise StepRuleBroken("旧外部意图的供应商或协议未在当前组装登记")
        adapter = self.adapter(spec)
        if adapter.simulated != row["simulated"]:
            raise StepRuleBroken("模拟意图不能通过真实适配器恢复")
        if binding_of(adapter) != row["binding"]:
            raise StepRuleBroken("外部意图的供应商账号或连接目标已改变，请使用原适配器查证")
        async with self.limits[spec]:
            attempt = await self.store.claim(id, spec, business_now(), lookup=lookup)
            if attempt is None:
                return final_result(self.result(spec, await self.store.read(id, caller)), lookup)
            await self.attempt(spec, adapter, row, id, attempt, records, effects, lookup)
        return final_result(self.result(spec, await self.store.read(id, caller)), lookup)

    @clocked
    async def attempt(
        self,
        spec: ProviderSpec,
        adapter: EffectAdapter,
        row: dict[str, Any],
        id: str,
        attempt: int,
        records: list[RemoteCallRecord],
        effects: list[RemoteCallRecord],
        lookup: bool,
    ) -> None:
        record = RemoteCallRecord(spec.name, "lookup" if lookup else spec.transport, id, 0, 0)
        record.effect = "read" if lookup else "write"
        record.endpoint, record.outcome = spec.name, "unknown"
        record.intent_id, record.provider_state, record.simulated = id, "unknown", adapter.simulated
        records.append(record)
        if not lookup:
            effects.append(record)
        started = monotonic()
        try:
            input = spec.input.model_validate_json(self.store.vault.decrypt(row["request"]))
            operation = adapter.lookup(input, id) if lookup else adapter.send(input, id)
            reply = await self.clock.run(operation, deadline=self.clock.monotonic() + spec.timeout)
            reply = checked_reply(spec, reply, lookup)
            if row["state"] == "accepted" and reply.state in {"not_sent", "refused", "unknown"}:
                raise StepRuleBroken("已受理的效果不能因查询未找到而改成未执行")
            if not await self.store.save(id, attempt, reply, business_now()):
                raise RemoteResultUnknown("迟到回执已保留，本次尝试不能改写新状态")
            record.outcome = {
                "accepted": "ok",
                "completed": "ok",
                "refused": "failed",
                "not_sent": "not_sent",
                "unknown": "unknown",
            }[reply.state]
            record.provider_state = reply.state
        except Exception as error:
            record.error = type(error).__name__
            raise RemoteResultUnknown("外部结果或本地回执尚不能确认，请查询原意图") from error
        except asyncio.CancelledError:
            record.error = "cancelled"
            raise
        finally:
            record.elapsed_ms = (monotonic() - started) * 1000

    def adapter(self, spec: ProviderSpec) -> EffectAdapter:
        if spec not in self.bindings:
            raise StepRuleBroken(f"外部效果 {spec.name} 未在产品组装登记")
        return self.bindings[spec]

    def result(self, spec: ProviderSpec, row: dict[str, Any]) -> EffectResult:
        data = (
            spec.output.model_validate_json(self.store.vault.decrypt(row["receipt"]))
            if row["receipt"]
            else None
        )
        return EffectResult(
            id=row["id"],
            state=row["state"],
            data=data,
            external_id=row["external_id"],
            simulated=row["simulated"],
        )


def checked_reply(spec: ProviderSpec, reply: AdapterReply, lookup: bool) -> AdapterReply:
    if reply.state not in {"not_sent", "refused", "accepted", "completed", "unknown"}:
        raise StepRuleBroken("供应商回执状态无效")
    if reply.state == "not_sent" and not lookup:
        raise StepRuleBroken("发送已开始，只能通过权威查询确认未执行")
    if reply.state in {"accepted", "completed"} and reply.data is None:
        raise StepRuleBroken("受理或完成必须具有明确回执")
    if lookup and reply.state == "not_sent" and reply.data is None:
        raise StepRuleBroken("确认未执行必须保留权威查询回执")
    if len(reply.external_id.encode()) > 200:
        raise StepRuleBroken("供应商编号超过200字节")
    data = spec.output.model_validate(reply.data) if reply.data is not None else None
    return AdapterReply(reply.state, data, reply.external_id)


def final_result(result: EffectResult, lookup: bool) -> EffectResult:
    if not lookup and result.state == "unknown":
        raise RemoteResultUnknown("原外部意图仍未确认或正在执行，不能盲目重发")
    if not lookup and result.state == "refused":
        raise RemoteRejected("供应商明确拒绝原外部意图，未自动重新发送")
    return result


def binding_of(adapter: EffectAdapter) -> str:
    if not adapter.identity or len(adapter.identity) > 1024:
        raise StepRuleBroken("供应商适配器必须声明有界账号与目标标识")
    return hashlib.sha256(adapter.identity.encode()).hexdigest()
