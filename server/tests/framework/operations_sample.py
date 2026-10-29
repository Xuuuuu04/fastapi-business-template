from shared.public import Data, Flow, JobPlan, Module, WorkData, contract, meaning, step


class Input(Data):
    pass


class Output(Data):
    ok: bool = meaning("操作实际完成", default=True)


class Work(WorkData):
    result: Output = meaning("执行结果")


@step("确认执行", writes=["result"])
async def complete(data: Work) -> None:
    data.result = Output()


critical = contract(
    "ops_sample.critical", "关键任务", input=Input, output=Output, access="ops_sample.run"
)
optional = contract(
    "ops_sample.optional", "非关键任务", input=Input, output=Output, access="ops_sample.run"
)
module = Module(
    name="ops_sample",
    title="独立运维样例",
    version="1",
    provides={
        op: Flow(op.title, work=Work, result="result", steps=[complete])
        for op in (critical, optional)
    },
    jobs=(JobPlan(critical, repeat_safe=True), JobPlan(optional, repeat_safe=True, critical=False)),
)
