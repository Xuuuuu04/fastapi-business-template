"""
查询与跨包写入的声明必须符合实际步骤，边界数据与领域字段分别检查。
"""

from typing import Any

from shared.modules.policy import check_policy
from shared.public import Data, Flow, Module, Nothing, WorkData, contract, meaning, step


# 无数据库的公开结果只用于声明检查。
class Work(WorkData):
    result: Nothing = meaning("空结果")


# 纯步骤通过明确结果完成。
@step("返回空结果", writes=["result"])
def produce(data: Work) -> None:
    data.result = Nothing()


# 查询不能把保存动作隐藏在下一层操作里。
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

    # 此声明只用于检查调用性质，不执行虚构存储。
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


# 能力包跨域命令必须由流程包承接，流程自身可以保存过程状态。
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

    # 引用声明只检查边界，不提供任何实际扣费实现。
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


# 不明确的业务字段必须列为边界输入，不能把任意字典包装成严格领域契约。
def test_opaque_data_requires_explicit_boundary() -> None:
    class Raw(Data):
        """明确需要迁移的旧表单原文。"""

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


# 查询自己不能保存业务数据，调用效果未知的旧约定同样算作写入风险。
def test_query_rejects_own_saves_and_unknown_effect() -> None:
    read = contract(
        "view_lists.read",
        "读取",
        input=Nothing,
        output=Nothing,
        access="view_lists.read",
        effect="query",
    )

    # 保存动作藏在查询自己的步骤里，同样开启共享写事务。
    @step("保存", writes=["result"], saves=True)
    def save(data: Work) -> None:
        data.result = Nothing()

    legacy = contract(
        "legacy_notes.read", "旧读取", input=Nothing, output=Nothing, access="legacy_notes.read"
    )

    # 旧约定没有声明效果，查询调用它时不能当作安全读取。
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


# 旧约定的效果由提供方决定，这里只给一个省略effect的读取声明。
def legacy_provider(legacy) -> Module:
    return Module(
        "legacy_notes",
        "旧记录",
        "1",
        {legacy: Flow("读取", work=Work, result="result", steps=[produce])},
        kind="capability",
    )


# 未声明kind的旧模块保持未知，不因新增检查被迫补全声明。
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


# 只读依赖必须指向登记过的模块，拼错的目标不能悄悄失去保护。
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

    # 引用声明只验证登记名称，不执行读取。
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
