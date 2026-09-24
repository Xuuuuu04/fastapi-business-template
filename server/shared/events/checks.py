"""
启动时检查事件声明：发布的事件由本模块声明，订阅的事件由已启用的模块发布，
处理操作属于订阅方模块、可以作为入口执行，输入类型与事件数据一致。
"""

from collections.abc import Sequence

from shared.events.event import Event, Subscription
from shared.flow.flow import Flow
from shared.modules.module import Module


# 检查全部模块的事件发布与订阅。
def check_events(modules: Sequence[Module]) -> list[str]:
    problems = []
    published: set[Event] = set()
    for module in modules:
        problems += [
            f"模块 {module.name} 发布的事件 {item.name} 必须以 {module.name}. 开头"
            for item in module.publishes
            if item.module != module.name
        ]
        published |= set(module.publishes)
        problems += check_publishing_steps(module)
    names = [item.name for item in published]
    problems += [f"事件名 {name} 重复" for name in sorted({n for n in names if names.count(n) > 1})]
    for module in modules:
        for sub in module.subscribes:
            problems += check_subscription(module, sub, published)
    return problems


# 检查一个订阅：事件有人发布，处理操作属于本模块、可作为入口、输入是事件数据、没有重复登记任务。
def check_subscription(module: Module, sub: Subscription, published: set[Event]) -> list[str]:
    place = f"模块 {module.name} 订阅的事件 {sub.event.name}"
    handler = sub.handler
    problems = []
    if sub.event not in published:
        problems.append(f"{place} 没有由任何已启用的模块发布")
    if handler not in module.provides:
        problems.append(f"{place} 的处理操作 {handler.name} 不是本模块提供的操作")
    if not handler.entry:
        problems.append(f"{place} 的处理操作 {handler.name} 必须可以作为入口执行")
    if handler.input is not sub.event.data:
        problems.append(
            f"{place} 的处理操作输入必须是事件数据 {sub.event.data.__name__}，"
            f"实际是 {handler.input.__name__}"
        )
    if any(plan.contract is handler for plan in module.jobs):
        problems.append(f"{place} 的处理操作已在 jobs 中声明，订阅会自动登记为任务，请删掉")
    return problems


# 步骤发布的事件必须在所在模块的 publishes 中声明。
def check_publishing_steps(module: Module) -> list[str]:
    return [
        f"模块 {module.name} 的步骤「{part.title}」发布的事件 {item.name} 没有在 publishes 中声明"
        for flow in module.provides.values()
        if isinstance(flow, Flow)
        for part in flow.steps
        for item in part.publishes
        if item not in module.publishes
    ]
