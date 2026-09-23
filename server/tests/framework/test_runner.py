"""
执行器测试：正常执行、条件跳过、失败回滚、嵌套调用共用事务、权限、超时、运行记录与中文摘要。
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.setup.build import Services
from shared.access.caller import ANONYMOUS, DEVELOPER, Caller
from shared.errors.framework import NotAllowed, NotSignedIn, RunTimeout, StepRuleBroken
from shared.records.stores import RunFilter
from tests.framework.sample_modules import (
    CalcInput,
    SlowInput,
    TextInput,
    calc,
    explain,
    hurried,
    notes,
    outer,
)

pytestmark = pytest.mark.anyio


# 读取示例表的行数。
async def count_notes(services: Services) -> int:
    async with services.database.read() as connection:
        return int(await connection.scalar(select(func.count()).select_from(notes)))


# 会员走优惠分支，结果写入数据库并提交。
async def test_member_gets_discount(sample: Services) -> None:
    result = await sample.runtime.run(
        calc, CalcInput(amount=Decimal("100"), vip=True), caller=DEVELOPER
    )
    assert result.total == Decimal("90.0")
    assert await count_notes(sample) == 1


# 非会员跳过优惠步骤，摘要说明跳过了哪一步。
async def test_skipped_step_is_recorded(sample: Services) -> None:
    await sample.runtime.run(calc, CalcInput(amount=Decimal("100")), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    assert [step.status for step in run.steps] == ["skipped", "ok", "ok", "ok"]
    assert "条件不满足而跳过：「计算优惠」" in run.summary
    assert "写入已提交" in run.summary


# 保存之后失败时，写入全部回滚，摘要说明停在哪一步。
async def test_failure_after_save_rolls_back(sample: Services) -> None:
    with pytest.raises(ValueError) as caught:
        await sample.runtime.run(
            calc, CalcInput(amount=Decimal("5"), fail_at="save"), caller=DEVELOPER
        )
    assert await count_notes(sample) == 0
    run = await sample.recorder.get(caught.value.run_id)  # type: ignore[attr-defined]
    assert run is not None and run.status == "failed"
    assert "在「保存结果」步骤停止" in run.summary
    assert "写入已全部撤销" in run.summary


# 下一层操作失败时，上一层已经写入的数据也一起回滚。
async def test_nested_failure_rolls_back_parent(sample: Services) -> None:
    with pytest.raises(ValueError):
        await sample.runtime.run(
            outer, CalcInput(amount=Decimal("5"), fail_at="save"), caller=DEVELOPER
        )
    assert await count_notes(sample) == 0


# 下一层操作沿用上一层的事务，能读到上一层刚写入的数据。
async def test_nested_call_shares_transaction(sample: Services) -> None:
    result = await sample.runtime.run(outer, CalcInput(amount=Decimal("5")), caller=DEVELOPER)
    assert result.saved == 2
    tree = await sample.recorder.tree((await sample.recorder.recent(RunFilter(), 1))[0].id)
    assert [run.contract for run in tree] == ["sample_outer.run", "sample_calc.calc"]
    assert tree[1].writes == "in_parent"


# 匿名调用受保护的操作报未登录，有身份但缺权限报无权限。
async def test_access_is_checked(sample: Services) -> None:
    with pytest.raises(NotSignedIn):
        await sample.runtime.run(calc, CalcInput(amount=Decimal("1")), caller=ANONYMOUS)
    stranger = Caller("key:x", "service", "x", frozenset({"other.read"}))
    with pytest.raises(NotAllowed):
        await sample.runtime.run(calc, CalcInput(amount=Decimal("1")), caller=stranger)
    assert await count_notes(sample) == 0


# 模块内的权限通配符 sample_calc.* 可以执行本模块的操作。
async def test_module_wildcard_permission(sample: Services) -> None:
    holder = Caller("key:y", "service", "y", frozenset({"sample_calc.*"}))
    result = await sample.runtime.run(calc, CalcInput(amount=Decimal("3")), caller=holder)
    assert result.total == Decimal("3")


# 超过操作的超时时间会停止等待，并报告超时。
async def test_timeout_is_reported(sample: Services) -> None:
    with pytest.raises(RunTimeout):
        await sample.runtime.run(hurried, SlowInput(seconds=1, mark="x"), caller=DEVELOPER)
    assert await count_notes(sample) == 0


# 传入类型不对的输入会指出期望的类型。
async def test_wrong_input_type(sample: Services) -> None:
    with pytest.raises(StepRuleBroken, match="需要 CalcInput"):
        await sample.runtime.run(calc, SlowInput(mark="x"), caller=DEVELOPER)  # type: ignore[arg-type]


# 大模型调用记录提示词名称、版本和模型。
async def test_model_call_is_recorded(sample: Services) -> None:
    result = await sample.runtime.run(explain, TextInput(mark="月报"), caller=DEVELOPER)
    assert result.text == "说明：请说明：月报"
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    call = run.steps[0].models[0]
    assert (call.prompt, call.version, call.model, call.status) == (
        "describe_mark",
        "3",
        "fake",
        "ok",
    )


# 字段声明了 log_value 才记录取值。
async def test_only_declared_values_are_logged(sample: Services) -> None:
    await sample.runtime.run(calc, CalcInput(amount=Decimal("100"), vip=True), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    values = {step.title: step.values for step in run.steps}
    assert values["计算应付"] == ["应付：90.0元"]
    assert values["计算优惠"] == ["优惠：已写入数字"]
