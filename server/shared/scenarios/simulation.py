"""
模拟骨架只在明确的测试运行中接收测试提供者；正式实现不能从确认预期生成。
"""

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


# 每个模拟提供者明确对应操作和步骤，不能靠同名结果字段猜来源。
@contextmanager
def simulate(providers: Mapping[tuple[str, str], Callable[[StepView], Any]]) -> Iterator[None]:
    token = CURRENT.set(dict(providers))
    try:
        yield
    finally:
        CURRENT.reset(token)


# 正式步骤照常执行；骨架必须在test环境显式注入，回调不取得框架存储或外部工具。
async def run_simulated(part: Step, view: StepView, operation: str, *, allowed: bool) -> Any:
    providers = CURRENT.get()
    if not allowed or providers is None or (operation, part.name) not in providers:
        raise StepRuleBroken("模拟骨架只能在test配置下使用明确的测试提供者")
    returned = providers[(operation, part.name)](view)
    return await returned if inspect.isawaitable(returned) else returned


# 生产在创建服务和执行任务前拒绝含模拟实现的声明。
def check_simulations(catalog: Catalog, env: str) -> None:
    if env == "production" and any(
        part.simulated for binding in catalog.bindings.values() for part in binding.flow.steps
    ):
        raise ConfigError(["生产配置不能包含模拟骨架，请先完成实际实现和交付检查"])


# 调用方也标记使用过模拟子操作，不能只看最外层真实步骤就把整链判为实际实现。
def mark_simulated(parent: RunRecord, step: StepRecord, child: RunRecord) -> None:
    parent.simulated = parent.simulated or child.simulated
    step.simulated = step.simulated or child.simulated
