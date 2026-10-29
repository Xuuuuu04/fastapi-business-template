from dataclasses import replace

from app.setup.catalog import MODULES as PROJECT_MODULES
from app.setup.structure import step_locations
from shared.flow.flow import Flow
from tests.architecture.sample_catalog import MODULES as SAMPLE_MODULES

MODULES = [*PROJECT_MODULES, *(replace(module, provides={}) for module in SAMPLE_MODULES)]


def test_computation_nodes_stay_in_steps() -> None:
    module = SAMPLE_MODULES[0]
    item, flow = next(iter(module.provides.items()))
    part = replace(flow.steps[0], func=test_computation_nodes_stay_in_steps)
    changed = Flow(
        flow.title, work=flow.work, result=flow.result, steps=(replace(part, when=None),)
    )
    problems = step_locations([replace(module, provides={item: changed})])
    assert len(problems) == 1 and "steps/" in problems[0]
