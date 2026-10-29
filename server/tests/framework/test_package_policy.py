from typing import Any

from shared.modules.policy import check_policy
from shared.public import Data, Flow, Module, Nothing, WorkData, contract, meaning, step


class Work(WorkData):
    result: Nothing = meaning("空结果")


@step("返回空结果", writes=["result"])
def produce(data: Work) -> None:
    data.result = Nothing()


def test_query_cannot_call_command() -> None:
    write = contract(
        "store_records.write",
        "写入",
        input=Nothing,
        output=Nothing,
        access="store_records.write",
        effect="command",
    )
    read = contract(
        "read_records.read",
        "读取",
        input=Nothing,
        output=Nothing,
        access="read_records.read",
        effect="query",
    )

    @step("调用写入", writes=["result"], uses=[write])
    async def call_write(data: Work, call) -> None:
        data.result = await call(write, Nothing())

    first = Module(
        "store_records",
        "存储",
        "1",
        {write: Flow("写入", work=Work, result="result", steps=[produce])},
    )
    second = Module(
        "read_records",
        "读取",
        "1",
        {read: Flow("读取", work=Work, result="result", steps=[call_write])},
        kind="capability",
    )
    assert any("不能调用" in problem for problem in check_policy([first, second]))


def test_capability_write_dependency_requires_workflow() -> None:
    target = contract(
        "quota_count.consume",
        "扣额度",
        input=Nothing,
        output=Nothing,
        access="quota_count.write",
        effect="command",
    )
    source = contract(
        "report_build.create",
        "生成",
        input=Nothing,
        output=Nothing,
        access="report_build.write",
        effect="command",
    )

    @step("扣额度", writes=["result"], uses=[target])
    async def consume(data: Work, call) -> None:
        data.result = await call(target, Nothing())

    provider = Module(
        "quota_count",
        "额度",
        "1",
        {target: Flow("额度", work=Work, result="result", steps=[produce])},
    )
    flow = Flow("生成", work=Work, result="result", steps=[consume])
    capability = Module("report_build", "报告", "1", {source: flow}, kind="capability")
    workflow = Module("report_build", "报告", "1", {source: flow}, kind="workflow")
    assert any("跨域写入" in issue for issue in check_policy([provider, capability]))
    assert check_policy([provider, workflow]) == []


def test_opaque_data_requires_explicit_boundary() -> None:
    class Raw(Data):
        values: dict[str, Any] = meaning("兼容输入")

    operation = contract(
        "raw_inputs.read",
        "读取",
        input=Raw,
        output=Nothing,
        access="raw_inputs.read",
        effect="query",
    )
    flow = Flow("读取", work=Work, result="result", steps=[produce])
    module = Module("raw_inputs", "兼容", "1", {operation: flow}, kind="capability")
    boundary = Module(
        "raw_inputs", "兼容", "1", {operation: flow}, kind="capability", boundary_data=(Raw,)
    )
    assert any("缺少明确类型" in issue for issue in check_policy([module]))
    assert check_policy([boundary]) == []


def test_query_rejects_own_saves_and_unknown_effect() -> None:
    read = contract(
        "view_lists.read",
        "读取",
        input=Nothing,
        output=Nothing,
        access="view_lists.read",
        effect="query",
    )

    @step("保存", writes=["result"], saves=True)
    def save(data: Work) -> None:
        data.result = Nothing()

    legacy = contract(
        "legacy_notes.read", "旧读取", input=Nothing, output=Nothing, access="legacy_notes.read"
    )

    @step("调用旧约定", writes=["result"], uses=[legacy])
    async def call_legacy(data: Work, call) -> None:
        data.result = await call(legacy, Nothing())

    saving = Module(
        "view_lists",
        "列表",
        "1",
        {read: Flow("读取", work=Work, result="result", steps=[save])},
        kind="capability",
    )
    calling = Module(
        "view_lists",
        "列表",
        "1",
        {read: Flow("读取", work=Work, result="result", steps=[call_legacy])},
        kind="capability",
    )
    assert any("不能保存" in issue for issue in check_policy([saving]))
    assert any("效果未知" in issue for issue in check_policy([calling, legacy_provider(legacy)]))


def legacy_provider(legacy) -> Module:
    return Module(
        "legacy_notes",
        "旧记录",
        "1",
        {legacy: Flow("读取", work=Work, result="result", steps=[produce])},
        kind="capability",
    )


def test_legacy_module_without_kind_stays_compatible() -> None:
    old = contract(
        "legacy_notes.read", "旧读取", input=Nothing, output=Nothing, access="legacy_notes.read"
    )
    module = Module(
        "legacy_notes",
        "旧记录",
        "1",
        {old: Flow("读取", work=Work, result="result", steps=[produce])},
    )
    assert check_policy([module]) == []


def test_read_dependencies_must_be_registered() -> None:
    target = contract(
        "source_records.read",
        "源读取",
        input=Nothing,
        output=Nothing,
        access="source_records.read",
        effect="query",
    )
    source = Module(
        "source_records",
        "来源",
        "1",
        {target: Flow("读取", work=Work, result="result", steps=[produce])},
        kind="capability",
    )

    @step("调用来源", writes=["result"], uses=[target])
    async def call_source(data: Work, call) -> None:
        data.result = await call(target, Nothing())

    flow = Flow("汇总", work=Work, result="result", steps=[call_source])
    declared = Module(
        "report_lists",
        "报表",
        "1",
        {
            contract(
                "report_lists.read",
                "汇总读取",
                input=Nothing,
                output=Nothing,
                access="report_lists.read",
                effect="query",
            ): flow
        },
        kind="capability",
        read_dependencies=("source_records",),
    )
    typoed = Module(
        declared.name,
        declared.title,
        "1",
        dict(declared.provides),
        kind="capability",
        read_dependencies=("source_recordz",),
    )
    assert check_policy([source, declared]) == []
    assert any("只读依赖未登记" in issue for issue in check_policy([source, typoed]))


def calling_module(name: str, kind: str, target: Any) -> Module:
    operation = contract(
        f"{name}.run", "执行", input=Nothing, output=Nothing, access=f"{name}.run", effect="command"
    )

    @step("调用", writes=["result"], uses=[target])
    async def call_target(data: Work, call) -> None:
        data.result = await call(target, Nothing())

    flow = Flow("执行", work=Work, result="result", steps=[call_target])
    return Module(name, "调用方", "1", {operation: flow}, kind=kind)


def test_nothing_calls_into_a_workflow() -> None:
    target = contract(
        "order_flow.start", "启动", input=Nothing, output=Nothing, access="a.b", effect="command"
    )
    owner = Module(
        "order_flow",
        "订单流程",
        "1",
        {target: Flow("启动", work=Work, result="result", steps=[produce])},
        kind="workflow",
    )
    for kind in ("workflow", "capability"):
        problems = check_policy([owner, calling_module("report_flow", kind, target)])
        assert any("不能调用流程包的操作 order_flow.start" in issue for issue in problems)


def test_workflow_owns_no_tables() -> None:
    from sqlalchemy import Column, Integer, MetaData, Table

    table = Table("order_flow_rows", MetaData(), Column("id", Integer, primary_key=True))
    expected = ["流程包 order_flow 不拥有数据表，表放到能力包"]
    for tables in ({"tables": (table,)}, {"owned_tables": ("x",)}, {"external_tables": ("y",)}):
        workflow = Module("order_flow", "订单流程", "1", {}, kind="workflow", **tables)
        assert check_policy([workflow]) == expected
