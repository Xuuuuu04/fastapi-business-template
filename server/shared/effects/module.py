"""
外部效果分发作为普通持久JobPlan运行，与业务任务共用领取、权限、取消和未知状态处理。
"""

from shared.data.fields import meaning
from shared.data.models import Data, Nothing, WorkData
from shared.effects.gate import EffectGate
from shared.effects.spec import ProviderSpec
from shared.flow.flow import Flow
from shared.flow.step import step
from shared.jobs.plan import JobPlan
from shared.modules.contract import contract
from shared.modules.module import Module


# 任务表只保存意图编号，正文仍由加密意图表管理。
class DispatchInput(Data):
    intent_id: str = meaning("已经登记的持久意图编号")


# 分发操作的输入与结果，不复制供应商正文到任务表。
class DispatchWork(WorkData):
    intent_id: str = meaning("持久意图编号")
    result: Nothing = meaning("本次意图已取得明确结果")


dispatch = contract(
    "system_effects.dispatch",
    "发送已提交外部意图",
    input=DispatchInput,
    output=Nothing,
    access="signed_in",
    effect="command",
)


# 只有登记了供应商能力的产品才加入内置分发操作。
def make_effect_module(providers: tuple[ProviderSpec, ...]) -> Module:
    # 未知结果抛异常进入任务unknown，不把单次模拟成功当作真实送达。
    @step("发送原外部意图", reads=["intent_id"], writes=["result"], providers=providers)
    async def send(data: DispatchWork, effects: EffectGate) -> None:
        await effects.perform(data.intent_id)
        data.result = Nothing()

    return Module(
        "system_effects",
        "持久外部效果",
        "3.0.0",
        {dispatch: Flow("分发意图", work=DispatchWork, result="result", steps=[send])},
        jobs=(JobPlan(dispatch),),
        providers=providers,
        kind="workflow",
    )
