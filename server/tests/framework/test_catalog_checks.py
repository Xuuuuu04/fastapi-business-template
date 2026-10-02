"""
模块目录检查的反例测试：重复登记、归属与权限命名、调用未登记的操作、循环依赖、表名、任务和定时计划。
"""

from datetime import time

import pytest

from shared.errors.framework import DeclarationError
from shared.modules.catalog import Catalog
from shared.public import Call, Flow, JobPlan, Module, Schedule, contract, step
from tests.framework.sample_modules import (
    CalcInput,
    CalcResult,
    OuterWork,
    SlowInput,
    calc,
    calc_flow,
    calc_module,
    call_calc,
    notes,
    outer_module,
    save_first,
    slow,
)


# 返回启动检查发现的问题。
def problems_of(*modules: Module) -> list[str]:
    with pytest.raises(DeclarationError) as caught:
        Catalog(list(modules))
    return caught.value.problems


# 示例模块本身通过检查，模块关系可以推出。
def test_sample_modules_pass() -> None:
    catalog = Catalog([calc_module, outer_module])
    assert catalog.links() == {"sample_calc": {}, "sample_outer": {"sample_calc": ["示例计算"]}}


# 同一个模块登记两次。
def test_duplicate_module() -> None:
    assert any(
        "模块名 sample_calc 重复登记" in item for item in problems_of(calc_module, calc_module)
    )


# 调用的操作所在模块没有启用。
def test_uses_disabled_module() -> None:
    problems = problems_of(outer_module)
    assert any(
        "调用了 sample_calc.calc，但提供它的模块没有登记或已关闭" in item for item in problems
    )


# 操作名前缀与模块名不一致，权限没有以模块名开头。
def test_ownership_and_access_names() -> None:
    wrong = contract("other.calc", "错位", input=CalcInput, output=CalcResult, access="admin")
    module = Module("sample_wrong", "错位", "1", provides={wrong: calc_flow})
    problems = problems_of(module)
    assert any("名称前缀必须是 sample_wrong." in item for item in problems)
    assert any(
        "权限 admin 必须是 public、signed_in 或以 sample_wrong. 开头" in item for item in problems
    )


# 两个模块互相调用形成循环。
def test_module_cycle() -> None:
    x_run = contract(
        "sample_x.run", "甲", input=CalcInput, output=CalcResult, access="sample_x.use"
    )
    y_run = contract(
        "sample_y.run", "乙", input=CalcInput, output=CalcResult, access="sample_y.use"
    )

    # 甲调用乙。
    @step("调用乙", reads=["amount"], writes=["result"], uses=[y_run])
    async def call_y(data: OuterWork, call: Call) -> None: ...

    # 乙调用甲。
    @step("调用甲", reads=["amount"], writes=["result"], uses=[x_run])
    async def call_x(data: OuterWork, call: Call) -> None: ...

    x_module = Module(
        "sample_x",
        "甲",
        "1",
        provides={x_run: Flow("甲", work=OuterWork, result="result", steps=[call_y])},
    )
    y_module = Module(
        "sample_y",
        "乙",
        "1",
        provides={y_run: Flow("乙", work=OuterWork, result="result", steps=[call_x])},
    )
    problems = problems_of(x_module, y_module)
    assert any("操作之间存在循环调用" in item for item in problems)
    assert any("模块之间存在循环依赖" in item for item in problems)


# 外层模块调用示例计算，关系图中有这条边。
def test_links_follow_uses() -> None:
    back = contract(
        "sample_back.run", "回调", input=CalcInput, output=CalcResult, access="sample_back.use"
    )
    back_flow = Flow("回调", work=OuterWork, result="result", steps=[save_first, call_calc])
    back_module = Module(
        "sample_back", "回调", "1", provides={back: back_flow}, store=calc_module.store
    )
    catalog = Catalog([calc_module, back_module])
    assert catalog.links()["sample_back"] == {"sample_calc": ["示例计算"]}


# 表名没有以模块名开头。
def test_table_prefix() -> None:
    module = Module("sample_table", "表名", "1", provides={}, tables=(notes,))
    assert any("必须以 sample_table_ 开头" in item for item in problems_of(module))


# 存储实现的构造参数写错名称，或者使用 remote 却没有声明外部系统。
def test_store_params() -> None:
    # 故意缺少操作的测试存储，用来检查模块声明错误。
    class WrongStore:
        # 参数名 database 和 remote 都不能直接使用。
        def __init__(self, database: object, remote: object) -> None:
            self.database, self.remote = database, remote

    module = Module("sample_store", "存储", "1", provides={}, store=WrongStore)
    problems = problems_of(module)
    assert any("不认识的构造参数 database" in item for item in problems)
    assert any("没有在 remotes 中声明外部系统" in item for item in problems)


# 任务声明了其他模块的操作；定时计划没有对应的任务声明、时间写法不对。
def test_jobs_and_schedules() -> None:
    plan = JobPlan(calc)
    timer = Schedule("wrong", "错误计划", slow, SlowInput(mark="x"), every=None, daily_at=None)
    module = Module("sample_jobs", "任务", "1", provides={}, jobs=(plan,), schedules=(timer,))
    problems = problems_of(module)
    assert any("不是模块 sample_jobs 提供的操作" in item for item in problems)
    assert any("需要先在 jobs 中声明" in item for item in problems)
    assert any("必须且只能设置 every 或 daily_at" in item for item in problems)


# 定时计划的时区写错。
def test_schedule_zone() -> None:
    timer = Schedule("t", "时区", slow, SlowInput(mark="x"), daily_at=time(2), zone="Mars/Base")
    module = Module(
        "sample_calc",
        calc_module.title,
        "1",
        provides=calc_module.provides,
        store=calc_module.store,
        prompts=calc_module.prompts,
        jobs=calc_module.jobs,
        schedules=(timer,),
    )
    assert any("时区 Mars/Base 无法识别" in item for item in problems_of(module))
