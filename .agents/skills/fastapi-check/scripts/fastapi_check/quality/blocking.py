import ast
from pathlib import Path

from fastapi_check.quality.report import Problem, files_under, relative
from fastapi_check.quality.rules import BLOCKING_CALLS, ROOT

from shared.modules.validation.imports import call_name


def check_blocking(root: Path = ROOT) -> list[Problem]:
    problems = []
    for path in files_under(root, ("app", "service", "shared"), ".py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                problems += blocking_calls(node, relative(path, root))
    return problems


def blocking_calls(function: ast.AsyncFunctionDef, name: str) -> list[Problem]:
    problems = []
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef):
            continue
        if isinstance(node, ast.Call) and full_name(node) in BLOCKING_CALLS:
            problems.append(
                Problem(
                    name,
                    node.lineno,
                    "blocking_call",
                    f"async 函数 {function.name} 中调用了会阻塞的 {full_name(node)}",
                    "改用异步写法，或把这段放进普通函数步骤并声明 heavy=True",
                )
            )
        pending.extend(ast.iter_child_nodes(node))
    return problems


def full_name(node: ast.Call) -> str:
    target = node.func
    parts = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts)) or call_name(node)
