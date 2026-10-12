"""
重复实现提示比较跨包函数的实际语法结构，只提示审查，不推定业务完全相同。
"""

import ast
import hashlib
from collections.abc import Iterator
from pathlib import Path


# 短包装函数不参与提示，忽略函数名称和首行文档，保留全部真实计算表达式。
def function_shape(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if len(body) < 4 or (node.end_lineno or node.lineno) - node.lineno < 8:
        return None
    shape = ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)
    return hashlib.sha256(shape.encode()).hexdigest()


# 仅列业务计算与步骤，框架、生成占位和测试数据不参与比较。
def business_files(project: Path) -> Iterator[tuple[str, Path]]:
    for folder in (project / "server/service").glob("*/"):
        for name in ("calc", "steps"):
            for path in (folder / name).rglob("*.py"):
                if not path.is_symlink() and "__pycache__" not in path.parts:
                    yield folder.name, path


# 同结构跨包实现保留源码出处，是否合并仍需结合实际业务判断。
def duplicate_hints(project: Path) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for package, path in business_files(project):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and (
                shape := function_shape(node)
            ):
                groups.setdefault(shape, []).append(
                    {
                        "package": package,
                        "source": path.relative_to(project).as_posix() + f":{node.lineno}",
                        "function": node.name,
                    }
                )
    return [
        {
            "locations": locations,
            "meaning": "跨包函数语法结构相同，请核对职责；这不证明业务语义相同",
        }
        for locations in groups.values()
        if len({location["package"] for location in locations}) > 1
    ]
