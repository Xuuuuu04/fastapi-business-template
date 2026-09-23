"""
OpenTelemetry 跨度：运行、跨模块调用和步骤形成父子关系，属性中没有业务字段的值。
"""

from decimal import Decimal

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.telemetry.service import Telemetry
from tests.framework.sample_modules import CalcInput, outer


# 外层操作调用计算操作：步骤跨度挂在所属运行下，下层运行挂在调用它的步骤下。
@pytest.mark.anyio
async def test_spans_follow_run_tree(sample: Services) -> None:
    exporter = InMemorySpanExporter()
    telemetry = Telemetry("", "test", exporter=exporter)
    sample.runtime.telemetry = telemetry
    try:
        await sample.runtime.run(outer, CalcInput(amount=Decimal("123.45")), caller=DEVELOPER)
    finally:
        telemetry.close()
    spans = exporter.get_finished_spans()
    by_id = {span.context.span_id: span for span in spans}
    runs = [span for span in spans if span.name == "run"]
    calls = [span for span in spans if span.name == "module_call"]
    assert len(runs) == 1 and len(calls) == 1
    assert {span.context.trace_id for span in spans} == {runs[0].context.trace_id}
    assert calls[0].parent is not None
    assert by_id[calls[0].parent.span_id].name == "step"
    for span in spans:
        if span.name == "step":
            assert span.parent is not None
            assert by_id[span.parent.span_id].name in ("run", "module_call")
        assert "123.45" not in str(dict(span.attributes or {}))
