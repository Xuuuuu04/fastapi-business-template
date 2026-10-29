import ast
import io
import tokenize
from pathlib import Path

from fastapi_check.quality.report import Problem, files_under, relative
from fastapi_check.quality.rules import (
    CODE_DIRS,
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
    MAX_NESTING,
    ROOT,
)

NESTED = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)
Function = ast.FunctionDef | ast.AsyncFunctionDef
DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
NO_TEXT = "用名字、类型和测试说清意图；修改原因写进提交说明"


def check_files(root: Path = ROOT) -> list[Problem]:
    problems = []
    for path in files_under(root, CODE_DIRS, ".py"):
        problems += check_file(path, root)
    return problems


def check_file(path: Path, root: Path = ROOT) -> list[Problem]:
    name = relative(path, root)
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    problems = check_comments(name, source) + check_docstrings(name, tree)
    if len(lines) > MAX_FILE_LINES:
        problems.append(
            Problem(
                name,
                0,
                "file_lines",
                f"文件有 {len(lines)} 行，超过 {MAX_FILE_LINES} 行",
                "按用途拆成几个文件，相近的函数放在一起",
            )
        )
    for node in ast.walk(tree):
        if isinstance(node, Function):
            problems += check_function(name, node)
    return problems


def check_comments(name: str, source: str) -> list[Problem]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [
        Problem(name, token.start[0], "comment", "代码里不写注释", NO_TEXT)
        for token in tokens
        if token.type == tokenize.COMMENT
    ]


def check_docstrings(name: str, tree: ast.Module) -> list[Problem]:
    return [
        Problem(name, node.body[0].lineno, "docstring", "代码里不写文档字符串", NO_TEXT)
        for node in ast.walk(tree)
        if isinstance(node, DOCUMENTED) and node.body and is_docstring(node.body[0])
    ]


def is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def check_function(name: str, node: Function) -> list[Problem]:
    problems = []
    length = (node.end_lineno or node.lineno) - node.lineno + 1
    if length > MAX_FUNCTION_LINES:
        problems.append(
            Problem(
                name,
                node.lineno,
                "function_lines",
                f"函数 {node.name} 有 {length} 行，超过 {MAX_FUNCTION_LINES} 行",
                "把可以独立说明的部分拆成函数或步骤",
            )
        )
    depth = nesting(node)
    if depth > MAX_NESTING:
        problems.append(
            Problem(
                name,
                node.lineno,
                "nesting",
                f"函数 {node.name} 嵌套 {depth} 层，超过 {MAX_NESTING} 层",
                "提前返回或拆出函数，减少嵌套",
            )
        )
    return problems


def nesting(node: ast.AST, depth: int = 0) -> int:
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, Function):
            continue
        is_elif = isinstance(node, ast.If) and node.orelse == [child] and isinstance(child, ast.If)
        inner = depth + 1 if isinstance(child, NESTED) and not is_elif else depth
        deepest = max(deepest, nesting(child, inner))
    return deepest
