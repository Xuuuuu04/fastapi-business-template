import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any

from shared.flow.step import Step, source_of


def check_calculations(part: Step, module: str) -> list[str]:
    problems = []
    prefix = f"service.{module}.calc."
    for func in part.calcs:
        if not inspect.isfunction(func) or not func.__module__.startswith((prefix, "library.")):
            problems.append(f"{part.source}：calcs 必须引用本模块calc或已声明的纯工具包")
        elif inspect.iscoroutinefunction(func):
            problems.append(f"{source_of(func)}：纯计算必须是同步函数，只接收参数并返回结果")
    try:
        called = direct_calculations(part.func)
    except (OSError, TypeError):
        if getattr(part.func, "__module__", "").startswith(("service.", "library.")):
            problems.append(f"{part.source}：无法读取源码，不能检查纯计算调用")
        called = []
    for func in called:
        if func not in part.calcs:
            problems.append(
                f"{part.source}：调用了 {source_of(func)}；请在 @step(calcs=[函数]) 登记"
            )
    return problems


def direct_calculations(func: Callable[..., Any]) -> list[Callable[..., Any]]:
    source = textwrap.dedent(inspect.getsource(func))
    tree = ast.parse(source)
    found: list[Callable[..., Any]] = []
    body = tree.body[0]
    nodes = [node for statement in getattr(body, "body", []) for node in ast.walk(statement)]
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        target = resolve(node.func, func.__globals__)
        if (
            inspect.isfunction(target)
            and (".calc." in target.__module__ or target.__module__.startswith("library."))
            and target not in found
        ):
            found.append(target)
    return found


def resolve(node: ast.expr, scope: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        return scope.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = resolve(node.value, scope)
        if inspect.ismodule(parent):
            return vars(parent).get(node.attr)
    return None
