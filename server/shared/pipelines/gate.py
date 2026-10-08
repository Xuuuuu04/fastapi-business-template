"""
流程启动步骤专用入口，只能启动当前登记的Pipeline，身份与事务沿用执行器。
"""

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.flow.scope import Scope
from shared.pipelines import member_tools
from shared.pipelines.plan import Member, MemberPage, PipelineView, StartRequest
from shared.records.models import RunRecord


# 框架生成的启动操作取得这个工具，业务阶段仍用原操作工具。
class PipelineGate:
    # 绑定当前公开操作和事务。
    def __init__(self, scope: Scope, run: RunRecord, *, saves: bool = True) -> None:
        self.scope, self.run = scope, run
        self.saves = saves

    # 创建或复用当前组织的周期，登记第一阶段与流程同事务提交。
    async def start(self, request: StartRequest) -> PipelineView:
        runtime = self.scope.runtime
        pipeline = runtime.catalog.pipeline_starts.get(self.run.contract)
        engine = getattr(runtime.jobs, "pipelines", None)
        if pipeline is None or engine is None:
            raise StepRuleBroken("pipeline工具只能由已登记的流程启动操作使用")
        connection = await self.scope.tx.writer(runtime.database, "启动流程")
        return await engine.start(connection, pipeline, request, self.scope.caller)

    # 取得声明过的固定来源，业务不查询当前最新版本。
    async def source[Source: Data](self, model: type[Source]) -> Source:
        return await member_tools.source(self, model)

    # 登记有界的一批成员，支持与分段游标一起提交。
    async def add_members(self, values: list[Member]) -> int:
        return await member_tools.add_members(self, values)

    # 获取已纳入汇合的成功成员，按键分页，不复制大结果。
    async def results[Output: Data](
        self, stage: str, model: type[Output], *, after: str = "", limit: int = 50
    ) -> MemberPage[Output]:
        return await member_tools.results(self, stage, model, after, limit)
