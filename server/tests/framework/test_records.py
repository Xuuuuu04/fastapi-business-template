"""
运行记录和图的测试：记录器出错不影响业务、内存保存有上限并计数、中文摘要、字段摘要不泄露内容、
流程图与字段来源、图中的文字转义。
"""

from decimal import Decimal

import pytest

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.data.fields import FieldNote
from shared.graphs.lineage import explain
from shared.graphs.mermaid import label
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from shared.records.models import RunRecord, StepRecord
from shared.records.stores import MemoryRunStore
from shared.records.summary import summarize
from shared.records.values import describe_value
from tests.framework.sample_modules import CalcInput, calc, calc_module

pytestmark = pytest.mark.anyio


# 故意保存失败的测试存储，用来检查记录不完整的提示。
class BrokenStore(MemoryRunStore):
    # 每次保存都失败，模拟排查存储不可用。
    async def save(self, runs: list[RunRecord]) -> None:
        raise OSError("排查存储不可用")


# 运行记录保存失败时，业务照常完成，失败次数被记下。
async def test_record_failure_does_not_break_business(sample: Services) -> None:
    sample.recorder.store = BrokenStore(10)
    result = await sample.runtime.run(calc, CalcInput(amount=Decimal("2")), caller=DEVELOPER)
    assert result.total == Decimal("2")
    assert sample.recorder.state().failures == 1


# 内存保存超过上限时丢弃最早的记录，并记下丢弃数量。
async def test_memory_store_limit() -> None:
    store = MemoryRunStore(2)
    runs = [
        RunRecord(
            str(index), str(index), "", "", "c", "t", "m", "1", "dev", "", "", "x", float(index)
        )
        for index in range(3)
    ]
    await store.save(runs)
    assert list(store.rows) == ["1", "2"] and store.dropped == 1


# 被拒绝的运行和失败的运行都有中文摘要。
def test_summaries() -> None:
    run = RunRecord("r", "r", "", "", "c", "创建报价", "m", "1", "dev", "", "", "x", 0.0)
    run.status, run.error_message = "refused", "需要权限 order_quote.write"
    assert summarize(run) == "“创建报价”没有执行：需要权限 order_quote.write。"
    step = StepRecord("s", "count", "计算金额", "compute", "R-02", "x.py:1", status="failed")
    step.error_place = "service/order_quote/steps/quote_rules.py:40"
    run.status, run.steps, run.planned = "failed", [step], ["count", "save", "build"]
    run.error_message, run.error_kind, run.writes = "价格缺失", "broken", "rolled_back"
    text = summarize(run)
    assert "在“计算金额”步骤停止：价格缺失" in text and "之后的 2 个步骤没有执行" in text
    assert "quote_rules.py:40" in text and "需要修改代码" in text and "数据库回滚" in text


# 字段摘要：默认只记录形状，声明了才记录取值，敏感字段从不记录。
def test_value_descriptions() -> None:
    plain = FieldNote("phone", "手机号")
    shown = FieldNote("total", "应付", unit="元", log_value=True)
    secret = FieldNote("token", "令牌", secret=True)
    assert describe_value("13800000000", plain) == "手机号：文本 11 字"
    assert describe_value(Decimal("9.50"), shown) == "应付：9.50元"
    assert describe_value("abc", secret) == "令牌：已写入（敏感字段，不记录内容）"
    assert (
        describe_value(None, FieldNote("x", "单价", empty="尚未定价")) == "单价：空，表示尚未定价"
    )


# 流程图列出步骤、条件和规则；字段来源逐层说明。
def test_flow_graph_and_lineage() -> None:
    binding = Catalog([calc_module]).bindings[calc]
    graph = flow_graph(binding)
    assert '|"条件：是会员"|' in graph and "计算应付（计算）" in graph
    lines = explain(binding, "result")
    assert lines[0].startswith("- 结果（result）：由步骤“整理结果”写入")
    assert any("应付（total）：由步骤“计算应付”写入" in line for line in lines)


# 图中的文字会被转义，输入内容不会被当成图语言执行。
def test_labels_are_escaped() -> None:
    assert label('A"]; click x call evil()') == "A&quot;]; click x call evil()"
    assert "<" not in label("<script>")
