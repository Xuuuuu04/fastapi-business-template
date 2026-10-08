"""
分段任务的启动检查：明确声明重试安全性，操作必须使用恢复游标。
普通任务误用 checkpoint 时在启动阶段指出声明位置。
"""

from shared.flow.flow import Flow
from shared.modules.module import Module


# 分段任务必须能安全重试本批，并直接声明它的恢复位置。
def check_segmented_jobs(module: Module) -> list[str]:
    problems = []
    for plan in module.jobs:
        flow = module.provides.get(plan.contract)
        has_checkpoint = isinstance(flow, Flow) and any(
            "checkpoint" in part.params for part in flow.steps
        )
        if not plan.segmented:
            if has_checkpoint:
                problems.append(
                    f"任务 {plan.contract.name} 使用 checkpoint，需要声明 segmented=True"
                )
            continue
        if not plan.repeat_safe:
            problems.append(f"分段任务 {plan.contract.name} 必须声明 repeat_safe=True")
        if isinstance(flow, Flow) and not has_checkpoint:
            problems.append(f"分段任务 {plan.contract.name} 必须使用 checkpoint 声明恢复位置")
    return problems
