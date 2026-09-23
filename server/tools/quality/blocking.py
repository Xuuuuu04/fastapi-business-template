"""
检查 async 函数中的阻塞调用。time.sleep、requests、同步数据库连接等会卡住整个服务的事件循环，
其他请求都要等它结束；在 async 函数中请改用 asyncio.sleep、httpx2.AsyncClient 和框架提供的 store。
"""

import ast
from pathlib import Path

from tools.quality.imports import call_name
from tools.quality.report import Problem, files_under, relative
from tools.quality.rules import BLOCKING_CALLS, ROOT


# 检查 app、service、shared 中全部 async 函数。
def check_blocking(root: Path = ROOT) -> list[Problem]:
    problems = []
    for path in files_under(root, ("app", "service", "shared"), ".py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                problems += blocking_calls(node, relative(path, root))
    return problems


# 找出一个 async 函数中直接出现的阻塞调用（不含其中定义的普通函数）。
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


# 取得调用的完整名称，支持 a.b.c 形式。
def full_name(node: ast.Call) -> str:
    target = node.func
    parts = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts)) or call_name(node)
