from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.flow.scope import Scope
from shared.pipelines import member_tools
from shared.pipelines.plan import Member, MemberPage, PipelineView, StartRequest
from shared.records.models import RunRecord


class PipelineGate:
    def __init__(self, scope: Scope, run: RunRecord, *, saves: bool = True) -> None:
        self.scope, self.run = scope, run
        self.saves = saves

    async def start(self, request: StartRequest) -> PipelineView:
        runtime = self.scope.runtime
        pipeline = runtime.catalog.pipeline_starts.get(self.run.contract)
        engine = getattr(runtime.jobs, "pipelines", None)
        if pipeline is None or engine is None:
            raise StepRuleBroken("pipeline 工具只能在已登记的流程启动操作中使用")
        connection = await self.scope.tx.writer(runtime.database, "启动流程")
        return await engine.start(connection, pipeline, request, self.scope.caller)

    async def source[Source: Data](self, model: type[Source]) -> Source:
        return await member_tools.source(self, model)

    async def add_members(self, values: list[Member]) -> int:
        return await member_tools.add_members(self, values)

    async def results[Output: Data](
        self, stage: str, model: type[Output], *, after: str = "", limit: int = 50
    ) -> MemberPage[Output]:
        return await member_tools.results(self, stage, model, after, limit)
