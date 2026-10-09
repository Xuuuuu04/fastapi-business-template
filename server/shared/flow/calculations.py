"""
检查步骤声明的纯计算函数，直接调用必须登记；允许经存储约定使用，耗时由步骤整体记录。
"""

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any

from shared.flow.step import Step, source_of


# 新calc调用要求明确登记；旧步骤没有calc时行为不变。
def check_calculations(part: Step, module: str) -> list[str]:
    problems = []
    prefix = f"service.{module}.calc."
    for func in part.calcs:
        if not inspect.isfunction(func) or not func.__module__.startswith(prefix):
            problems.append(f"{part.source}：calcs 必须引用本模块 calc/ 中的函数")
        elif inspect.iscoroutinefunction(func):
            problems.append(f"{source_of(func)}：纯计算必须是同步函数，只接收参数并返回结果")
    called = direct_calculations(part.func)
    for func in called:
        if func not in part.calcs:
            problems.append(
                f"{part.source}：调用了 {source_of(func)}；请在 @step(calcs=[函数]) 登记"
            )
    return problems


# 识别函数别名和模块属性调用，不执行计算，也不读取数据库。
def direct_calculations(func: Callable[..., Any]) -> list[Callable[..., Any]]:
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return []
    tree = ast.parse(source)
    found: list[Callable[..., Any]] = []
    body = tree.body[0]
    nodes = [node for statement in getattr(body, "body", []) for node in ast.walk(statement)]
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        target = resolve(node.func, func.__globals__)
        if inspect.isfunction(target) and ".calc." in target.__module__ and target not in found:
            found.append(target)
    return found


# 仅查已有模块属性，避免执行属性描述符。
def resolve(node: ast.expr, scope: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        return scope.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = resolve(node.value, scope)
        if inspect.ismodule(parent):
            return vars(parent).get(node.attr)
    return None
