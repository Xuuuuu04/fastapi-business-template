"""
Mermaid 图的调用样式兼容性：避免把语法关键字当作样式名称。
"""

from shared.graphs.observed import run_graph
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from tests.framework.sample_modules import calc, calc_module, outer, outer_module


# 跨模块调用保留业务种类，只在图中使用不会触发 call 语法的样式名。
def test_call_step_uses_parser_safe_style() -> None:
    binding = Catalog([calc_module, outer_module]).bindings[outer]
    graph = flow_graph(binding)
    assert binding.flow.steps[1].kind == "call"
    assert 's2["2. 调用示例计算（调用）' in graph
    assert ":::invoke" in graph
    assert "classDef invoke fill:#f5f0ff,stroke:#7a5ab5" in graph
    assert "classDef call " not in graph
    assert ":::call" not in graph


# 即使流程没有调用步骤，共用样式也不能包含 Mermaid 的 call 关键字。
def test_graph_without_calls_has_parser_safe_styles() -> None:
    graph = flow_graph(Catalog([calc_module]).bindings[calc])
    assert "classDef call " not in graph
    assert "classDef invoke " in graph


# 实际执行图同样复用这份样式，不能再次引入解析失败。
def test_execution_graph_has_parser_safe_styles() -> None:
    graph = run_graph([])
    assert "classDef call " not in graph
    assert "classDef invoke " in graph
