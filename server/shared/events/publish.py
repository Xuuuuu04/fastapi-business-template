"""
步骤中的 publish 工具：发布一个事件，为每个订阅方在本次写入事务中登记一个后台任务。
订阅方以“事件”身份执行：只拥有处理这个事件所需的权限，组织范围沿用发布时的调用者。
"""

from typing import TYPE_CHECKING, Any

from shared.access.caller import Caller
from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.events.event import Event
from shared.modules.contract import Contract

if TYPE_CHECKING:
    from shared.flow.scope import Scope
    from shared.flow.step import Step
    from shared.records.models import RunRecord, StepRecord


class Publisher:
    # 绑定本次运行、步骤记录和步骤声明可发布的事件。
    def __init__(
        self, scope: "Scope", run: "RunRecord", record: "StepRecord", part: "Step"
    ) -> None:
        self._scope, self._run, self._record, self._part = scope, run, record, part
        self._count = 0

    # 发布事件；返回为订阅方登记的任务编号，没有订阅方时返回空列表。
    async def __call__(self, item: Event, data: Data) -> list[str]:
        runtime = self._scope.runtime
        if item not in self._part.publishes:
            raise StepRuleBroken(
                f"步骤「{self._part.title}」发布了未声明的事件 {item.name}，请在 publishes 中声明"
            )
        if not isinstance(data, item.data):
            raise StepRuleBroken(
                f"事件 {item.name} 需要 {item.data.__name__}，实际是 {type(data).__name__}"
            )
        if runtime.jobs is None:
            raise StepRuleBroken("没有启用后台任务功能，不能发布事件")
        self._count += 1
        connection = await self._scope.tx.writer(runtime.database, self._part.title)
        job_ids = []
        for handler in runtime.catalog.handlers(item):
            caller = event_caller(item, handler, self._scope.caller)
            key = f"{self._run.id}:{self._part.name}:{self._count}"
            job_ids.append(
                await runtime.jobs.submit(
                    connection, handler, data, caller, key=key, request_id=self._scope.request_id
                )
            )
        self._record.notes.append(f"发布事件「{item.title}」，{len(job_ids)} 个订阅方")
        return job_ids


# 订阅方执行时的身份：只拥有处理操作的权限，组织范围与发布时相同。
def event_caller(item: Event, handler: Contract[Any, Any], origin: Caller) -> Caller:
    return Caller(
        f"event:{item.name}",
        "event",
        f"事件「{item.title}」",
        frozenset({handler.access}),
        origin.org_id,
    )
