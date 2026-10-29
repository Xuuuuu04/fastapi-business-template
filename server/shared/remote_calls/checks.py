import ast
import inspect
import textwrap
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from shared.flow.flow import Flow
from shared.remote_calls.endpoint import Endpoint, endpoint_problems

if TYPE_CHECKING:
    from shared.flow.step import Step
    from shared.modules.module import Module


def check_endpoints(modules: Sequence["Module"]) -> list[str]:
    problems: list[str] = []
    defined: dict[str, Endpoint[Any, Any]] = {}
    for module in modules:
        local: set[str] = set()
        for endpoint in module.endpoints:
            previous = defined.setdefault(endpoint.name, endpoint)
            if endpoint.name in local or previous is not endpoint:
                problems.append(f"上游接口 {endpoint.name} 重复定义，请从public复用同一声明")
            local.add(endpoint.name)
            problems += endpoint_problems(endpoint)
        for flow in module.provides.values():
            if not isinstance(flow, Flow):
                continue
            for part in flow.steps:
                problems += check_step_endpoints(module, part)
    return problems


def check_step_endpoints(module: "Module", part: "Step") -> list[str]:
    place = f"步骤“{part.title}”（{part.source}）"
    problems = []
    for endpoint in part.endpoints:
        if endpoint not in module.endpoints:
            problems.append(f"{place} 上游接口 {endpoint.name} 未在Module.endpoints登记")
    if part.endpoints and not ({"store", "remote"} & set(part.params)):
        problems.append(f"{place} 声明endpoints但没有store或remote参数")
    problems += inspect_calls(part.func, part.endpoints, place)
    if "store" in part.params and module.store is not None:
        for name, method in inspect.getmembers(module.store, inspect.isfunction):
            if name not in store_methods(part.func):
                continue
            problems += inspect_calls(method, part.endpoints, f"存储 {method.__qualname__}")
        if part.endpoints and not module.remotes:
            problems.append(f"{place} 没有在Module.remotes登记外部系统")
    return problems


def inspect_calls(func: Any, allowed: tuple[Endpoint[Any, Any], ...], place: str) -> list[str]:
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    except (OSError, TypeError, IndentationError):
        return []
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = node.func.value
        remote = (isinstance(receiver, ast.Name) and receiver.id == "remote") or (
            isinstance(receiver, ast.Attribute) and receiver.attr == "remote"
        )
        if not remote:
            continue
        if node.func.attr == "call":
            reference = (
                node.args[1]
                if len(node.args) > 1
                else next((kw.value for kw in node.keywords if kw.arg == "endpoint"), None)
            )
            value = resolve(reference, getattr(func, "__globals__", {}))
            if not allowed or (isinstance(value, Endpoint) and value not in allowed):
                name = value.name if isinstance(value, Endpoint) else "未知（动态选择）"
                problems.append(f"{place} 调用了未声明的上游接口 {name}，请补endpoints")
    return problems


def resolve(node: ast.expr | None, namespace: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        return namespace.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = resolve(node.value, namespace)
        return vars(parent).get(node.attr) if hasattr(parent, "__dict__") else None
    return None


def store_methods(func: Any) -> set[str]:
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    except (OSError, TypeError, IndentationError):
        return set()
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "store"
    }
