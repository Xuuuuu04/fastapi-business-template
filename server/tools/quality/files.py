"""
检查 Python 文件的写法：文件头多行中文说明、类的用途说明、函数前单行中文说明、待办标记、
文件和函数长度、嵌套层数、函数体内的连续注释。
"""

import ast
import io
import re
import tokenize
from pathlib import Path

from tools.quality.report import Problem, files_under, relative
from tools.quality.rules import (
    CODE_DIRS,
    MAX_COMMENT_RUN,
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
    MAX_NESTING,
    ROOT,
    TODO_WORDS,
)

CHINESE = re.compile(r"[一-鿿]")
NESTED = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)
Function = ast.FunctionDef | ast.AsyncFunctionDef


# 检查全部 Python 文件。
def check_files(root: Path = ROOT) -> list[Problem]:
    problems = []
    for path in files_under(root, CODE_DIRS, ".py"):
        problems += check_file(path, root)
    return problems


# 检查一个 Python 文件。
def check_file(path: Path, root: Path = ROOT) -> list[Problem]:
    name = relative(path, root)
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    problems = check_header(name, source, tree)
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
    problems += check_todo(name, source)
    for node in ast.walk(tree):
        if isinstance(node, Function):
            problems += check_function(name, node, lines)
        elif isinstance(node, ast.ClassDef):
            problems += check_class(name, node, lines)
    return problems


# 检查类的用途说明，可以写在类或装饰器前，也可以写成类内文档字符串。
def check_class(name: str, node: ast.ClassDef, lines: list[str]) -> list[Problem]:
    start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
    above = lines[start - 2].strip() if start >= 2 else ""
    doc = ast.get_docstring(node) or ""
    if CHINESE.search(doc) or (above.startswith("# ") and CHINESE.search(above)):
        return []
    return [Problem(name, node.lineno, "class_comment", f"类 {node.name} 缺少中文用途说明")]


# 检查文件头说明：必须是多行中文文档字符串。
def check_header(name: str, source: str, tree: ast.Module) -> list[Problem]:
    doc = ast.get_docstring(tree)
    if not doc or not source.startswith('"""\n'):
        return [
            Problem(name, 1, "file_header", "缺少多行文件说明", '文件开头写 """ 换行，说明文件用途')
        ]
    if not CHINESE.search(doc):
        return [Problem(name, 1, "file_header", "文件说明需要用中文写")]
    return []


# 检查注释中的待办标记；只看真正的注释，不看字符串。
def check_todo(name: str, source: str) -> list[Problem]:
    pattern = re.compile(r"\b(" + "|".join(TODO_WORDS) + r")\b")
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [
        Problem(
            name,
            token.start[0],
            "todo",
            "代码中不留待办标记",
            "未完成的事项记到 doc/tasks.md，待定的业务问题在 rules.md 中标“待确认”",
        )
        for token in tokens
        if token.type == tokenize.COMMENT and pattern.search(token.string)
    ]


# 检查函数：前一行单行中文说明、长度、嵌套、函数体内连续注释。
def check_function(name: str, node: Function, lines: list[str]) -> list[Problem]:
    problems = []
    start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
    above = lines[start - 2].strip() if start >= 2 else ""
    if not (above.startswith("# ") and CHINESE.search(above)):
        problems.append(
            Problem(
                name,
                node.lineno,
                "function_comment",
                f"函数 {node.name} 前缺少单行中文说明",
                "在函数或装饰器上一行写“# 做什么”",
            )
        )
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
    problems += check_comment_runs(name, node, lines)
    return problems


# 计算函数中最深的嵌套层数；elif 与它前面的 if 算同一层。
def nesting(node: ast.AST, depth: int = 0) -> int:
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, Function):
            continue
        is_elif = isinstance(node, ast.If) and node.orelse == [child] and isinstance(child, ast.If)
        inner = depth + 1 if isinstance(child, NESTED) and not is_elif else depth
        deepest = max(deepest, nesting(child, inner))
    return deepest


# 检查函数体内连续注释的行数，避免记录修错经过和大段解释。
def check_comment_runs(name: str, node: Function, lines: list[str]) -> list[Problem]:
    run, problems = 0, []
    for number in range(node.lineno + 1, (node.end_lineno or node.lineno) + 1):
        run = run + 1 if lines[number - 1].strip().startswith("#") else 0
        if run == MAX_COMMENT_RUN + 1:
            problems.append(
                Problem(
                    name,
                    number,
                    "comment_run",
                    f"函数 {node.name} 内有连续 {run} 行以上的注释",
                    "注释只说明必要原因；修改经过写进提交说明",
                )
            )
    return problems
