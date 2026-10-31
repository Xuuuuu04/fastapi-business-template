import ast
import re
from pathlib import Path

from fastapi_check.quality.rules import PROJECT, ROOT

NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def validate(module: str, name: str) -> Path:
    if not NAME.fullmatch(module) or not NAME.fullmatch(name):
        raise ValueError("模块和操作名只能使用小写字母、数字、下划线")
    folder = ROOT / "service" / module
    if folder.is_symlink() or not (folder / "module.json").is_file():
        raise ValueError("需要一个按模板创建的业务包，请先用 uv run dev new-module 生成")
    return folder


def extend_module(text: str, keyword: str, entry: str, *, mapping: bool = False) -> str:
    tree = ast.parse(text)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Module"
    ]
    if len(calls) != 1:
        raise ValueError("module.py 必须包含且只包含一个 Module 声明")
    call = calls[0]
    found = next((item.value for item in call.keywords if item.arg == keyword), None)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    if found is not None:
        assert found.end_lineno is not None and found.end_col_offset is not None
        if not isinstance(found, ast.Dict if mapping else ast.Tuple):
            raise ValueError(f"{keyword} 必须直接写成字典或元组，不能由函数或变量计算得到")
        start = offsets[found.lineno - 1] + column(lines[found.lineno - 1], found.col_offset)
        end = offsets[found.end_lineno - 1] + column(
            lines[found.end_lineno - 1], found.end_col_offset
        )
        original = text[start:end].rstrip()
        inner = original[1:-1].rstrip().rstrip(",")
        opening, closing = ("{", "}") if mapping else ("(", ")")
        replacement = opening + inner + (",\n" if inner else "\n") + entry + ",\n" + closing
        return text[:start] + replacement + text[end:]
    assert call.end_lineno is not None and call.end_col_offset is not None
    end = offsets[call.end_lineno - 1] + column(lines[call.end_lineno - 1], call.end_col_offset) - 1
    value = "{" + entry + "}" if mapping else "(" + entry + ",)"
    return text[:end] + f"\n    {keyword}={value},\n" + text[end:]


def append(text: str, code: str) -> str:
    return text.rstrip() + "\n\n" + code.strip() + "\n"


def write(changes: dict[Path, str], *, preview: bool = False) -> list[str]:
    actual = {
        path: value
        for path, value in changes.items()
        if not path.exists() or path.read_text() != value
    }
    if not preview:
        for path, value in actual.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
    return [str(path.relative_to(PROJECT)) for path in actual]


def column(line: str, byte_offset: int) -> int:
    return len(line.encode("utf-8")[:byte_offset].decode("utf-8"))


def add_import(text: str, line: str) -> str:
    tree = ast.parse(text)
    after = 0
    for node in tree.body:
        if (
            (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            or isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
        ):
            after = node.end_lineno or node.lineno
        else:
            break
    lines = text.splitlines(keepends=True)
    return "".join(lines[:after]) + "\n" + line + "\n" + "".join(lines[after:])


def snapshot(paths: list[Path]) -> dict[Path, str | None]:
    return {path: path.read_text() if path.exists() else None for path in paths}
