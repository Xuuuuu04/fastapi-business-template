from shared.data.fields import meaning
from shared.data.models import Data, Nothing, WorkData
from shared.effects.gate import EffectGate
from shared.effects.spec import ProviderSpec
from shared.flow.flow import Flow
from shared.flow.step import step
from shared.jobs.plan import JobPlan
from shared.modules.contract import contract
from shared.modules.module import Module


class DispatchInput(Data):
    intent_id: str = meaning("已保存的外部请求记录编号，用于发送或查询原请求")


class DispatchWork(WorkData):
    intent_id: str = meaning("已保存的外部请求记录编号")
    result: Nothing = meaning("外部请求已处理，无返回字段")


dispatch = contract(
    "system_effects.dispatch",
    "发送已保存的外部请求",
    input=DispatchInput,
    output=Nothing,
    access="signed_in",
    effect="command",
)


def make_effect_module(providers: tuple[ProviderSpec, ...]) -> Module:
    @step("发送原外部请求", reads=["intent_id"], writes=["result"], providers=providers)
    async def send(data: DispatchWork, effects: EffectGate) -> None:
        await effects.perform(data.intent_id)
        data.result = Nothing()

    return Module(
        "system_effects",
        "外部请求发送与结果记录",
        "3.0.0",
        {dispatch: Flow("发送外部请求", work=DispatchWork, result="result", steps=[send])},
        jobs=(JobPlan(dispatch),),
        providers=providers,
        kind="workflow",
    )
