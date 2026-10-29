from collections.abc import Sequence
from pathlib import Path

from shared.errors.framework import ConfigError
from shared.flow.step import Condition, Step
from shared.modules.layout import check_layout, declared_kind
from shared.modules.module import Module
from shared.modules.validation.imports import check_imports

ROOT = Path(__file__).resolve().parents[2]


def check_structure(
    modules: Sequence[Module], root: Path = ROOT, *, strict: bool | None = None
) -> None:
    problems = check_layout(root, (module.name for module in modules))
    problems += step_locations(modules)
    problems += [
        f"service/{module.name}：module.json 写的是 {kind}，module.py 写的是 {module.kind}"
        for module in modules
        if (kind := declared_kind(root / "service" / module.name)) and kind != module.kind
    ]
    problems += [problem.text() for problem in check_imports(root, strict=strict)]
    if problems:
        raise ConfigError(problems)


def step_locations(modules: Sequence[Module]) -> list[str]:
    problems = []
    for module in modules:
        prefix = f"service.{module.name}.steps."
        parts = (part for flow in module.provides.values() for part in flow.steps)
        for part in parts:
            nodes: list[Step | Condition] = [part]
            if part.when:
                nodes.append(part.when)
            for node in nodes:
                if not node.func.__module__.startswith(prefix):
                    problems.append(
                        f"{node.source}：计算节点 {node.name} "
                        f"必须写在 service/{module.name}/steps/ 中"
                    )
    return problems
