"""
时间预算的静态诊断，指出上层期限小于下层配置的位置，不把排队或业务有效期混成调用超时。
"""

from typing import Any

from shared.config.settings import Settings
from shared.modules.catalog import Catalog


# 配置默认值与运行观察分开，静态诊断不执行操作、不查询数据库。
def budget_report(catalog: Catalog, settings: Settings) -> dict[str, Any]:
    rows, issues = [], []
    for operation, binding in sorted(catalog.by_name.items()):
        plan = catalog.plan(operation)
        limits = dict(
            operation=binding.contract.timeout,
            queue=plan.queue_timeout if plan else None,
            attempt=plan.attempt_timeout if plan else None,
            lease=plan.lease_seconds if plan else None,
            validity_field=plan.valid_until_field if plan else "",
        )
        calls = lower_budgets(catalog, operation, settings)
        upper = (
            min(binding.contract.timeout, plan.attempt_timeout)
            if plan and plan.attempt_timeout
            else binding.contract.timeout
        )
        for call in calls:
            if call["seconds"] > upper:
                issues.append(
                    dict(
                        operation=operation,
                        source=call["source"],
                        kind=call["kind"],
                        upper_seconds=upper,
                        lower_seconds=call["seconds"],
                        message="上层预算早于下层配置，超过上层期限将停止等待",
                    )
                )
        rows.append(dict(operation=operation, budgets=limits, calls=calls))
    return dict(operations=rows, issues=issues, observation="声明与配置，不是实际耗时")


# 只有同步调用的预算互相比较；Pipeline等待阶段的长期有效期不与单次轮询混用。
def lower_budgets(catalog: Catalog, operation: str, settings: Settings) -> list[dict[str, Any]]:
    binding = catalog.by_name[operation]
    calls = []
    for part in binding.flow.steps:
        calls += [
            dict(kind="operation", name=target.name, seconds=target.timeout, source=part.source)
            for target in part.uses
        ]
        calls += [
            dict(kind="provider", name=provider.name, seconds=provider.timeout, source=part.source)
            for provider in part.providers
        ]
        for remote in part.remotes:
            config = settings.remotes.get(remote.name)
            seconds = config.timeout if config and config.timeout else remote.timeout
            calls.append(dict(kind="remote", name=remote.name, seconds=seconds, source=part.source))
        if "model" in part.params:
            calls.append(
                dict(kind="model", name="model", seconds=settings.model_timeout, source=part.source)
            )
    return calls
