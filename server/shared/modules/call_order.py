from typing import Any

from shared.flow.flow import Flow
from shared.flow.step import Step
from shared.modules.contract import Contract

Flows = dict[Contract[Any, Any], Flow]
Effects = tuple[bool, bool]


def call_effects(flows: Flows) -> dict[Contract[Any, Any], Effects]:
    memo: dict[Contract[Any, Any], Effects] = {}

    def visit(item: Contract[Any, Any], visiting: set[Contract[Any, Any]]) -> Effects:
        if item in memo:
            return memo[item]
        flow = flows.get(item)
        if not isinstance(flow, Flow) or item in visiting:
            return False, False
        children = [visit(used, visiting | {item}) for part in flow.steps for used in part.uses]
        result = (
            any(part.saves for part in flow.steps) or any(write for write, _ in children),
            any(outside_transaction(part) for part in flow.steps)
            or any(external for _, external in children),
        )
        memo[item] = result
        return result

    for item in flows:
        visit(item, set())
    return memo


def check_call_order(flows: Flows) -> list[str]:
    effects = call_effects(flows)
    problems = []
    for item, flow in flows.items():
        saving = ""
        for part in flow.steps if isinstance(flow, Flow) else ():
            children = [effects.get(used, (False, False)) for used in part.uses]
            external = outside_transaction(part) or any(external for _, external in children)
            if saving and external:
                problems.append(
                    f"操作 {item.name} 的步骤“{part.title}”在写入事务开始后调用外部服务；"
                    f"写入来源是“{saving}”，请把外部调用移到它之前"
                )
            if not saving and (part.saves or any(write for write, _ in children)):
                saving = part.title
    return problems


def outside_transaction(item: Step) -> bool:
    return bool({"model", "remote"} & set(item.params)) or (
        "effects" in item.params and not item.saves
    )
