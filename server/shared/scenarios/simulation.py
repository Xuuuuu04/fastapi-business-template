import inspect
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from shared.errors.framework import ConfigError, StepRuleBroken
from shared.flow.step import Step
from shared.flow.view import StepView
from shared.modules.catalog import Catalog
from shared.records.models import RunRecord, StepRecord

CURRENT: ContextVar[Mapping[tuple[str, str], Callable[[StepView], Any]] | None] = ContextVar(
    "scenario_simulation",
    default=None,
)


@contextmanager
def simulate(providers: Mapping[tuple[str, str], Callable[[StepView], Any]]) -> Iterator[None]:
    token = CURRENT.set(dict(providers))
    try:
        yield
    finally:
        CURRENT.reset(token)


async def run_simulated(part: Step, view: StepView, operation: str, *, allowed: bool) -> Any:
    providers = CURRENT.get()
    if not allowed or providers is None or (operation, part.name) not in providers:
        raise StepRuleBroken("模拟骨架只能在test配置下使用明确的测试提供者")
    returned = providers[(operation, part.name)](view)
    return await returned if inspect.isawaitable(returned) else returned


def check_simulations(catalog: Catalog, env: str) -> None:
    if env == "production" and any(
        part.simulated for binding in catalog.bindings.values() for part in binding.flow.steps
    ):
        raise ConfigError(["生产配置不能包含模拟骨架，请先完成实际实现和交付检查"])


def mark_simulated(parent: RunRecord, step: StepRecord, child: RunRecord) -> None:
    parent.simulated = parent.simulated or child.simulated
    step.simulated = step.simulated or child.simulated
