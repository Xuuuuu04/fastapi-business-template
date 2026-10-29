from shared.graphs.observed import run_graph
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from tests.framework.sample_modules import calc, calc_module, outer, outer_module


def test_call_step_uses_parser_safe_style() -> None:
    binding = Catalog([calc_module, outer_module]).bindings[outer]
    graph = flow_graph(binding)
    assert binding.flow.steps[1].kind == "call"
    assert 's2["2. 调用示例计算' in graph
    assert "（调用）" not in graph
    assert ":::invoke" in graph
    assert "classDef invoke fill:#f5f0ff,stroke:#7a5ab5" in graph
    assert "classDef call " not in graph
    assert ":::call" not in graph


def test_graph_without_calls_has_parser_safe_styles() -> None:
    graph = flow_graph(Catalog([calc_module]).bindings[calc])
    assert "classDef call " not in graph
    assert "classDef invoke " in graph


def test_execution_graph_has_parser_safe_styles() -> None:
    graph = run_graph([])
    assert "classDef call " not in graph
    assert "classDef invoke " in graph
