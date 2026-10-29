import ast
import hashlib
from collections.abc import Iterator
from pathlib import Path


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


def business_files(project: Path) -> Iterator[tuple[str, Path]]:
    for folder in (project / "server/service").glob("*/"):
        for name in ("calc", "steps"):
            for path in (folder / name).rglob("*.py"):
                if not path.is_symlink() and "__pycache__" not in path.parts:
                    yield folder.name, path


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
