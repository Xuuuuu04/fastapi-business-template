"""
生成器的可审查文件改动：先计算全部目标，再写入；AST只定位登记表达式，保留其余源码。
"""

import ast
import re
from pathlib import Path

from fastapi_check.quality.rules import PROJECT, ROOT

NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


# 目标只允许已有标准模块内的简单名称，避免路径或代码片段进入生成器。
def validate(module: str, name: str) -> Path:
    if not NAME.fullmatch(module) or not NAME.fullmatch(name):
        raise ValueError("模块和操作名只能使用小写字母、数字、下划线")
    folder = ROOT / "service" / module
    if folder.is_symlink() or not (folder / "module.json").is_file():
        raise ValueError("需要已有标准模块，请先new_module或adopt_modules")
    return folder


# 把新项加入Module的一个字典或元组声明，不改无关函数和注释。
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
        raise ValueError("module.py需要一个明确的Module声明")
    call = calls[0]
    found = next((item.value for item in call.keywords if item.arg == keyword), None)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    if found is not None:
        assert found.end_lineno is not None and found.end_col_offset is not None
        if not isinstance(found, ast.Dict if mapping else ast.Tuple):
            raise ValueError(f"{keyword}需要字典或元组声明，请先改成可直接登记的写法")
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


# public导出以追加形式扩展，保留产品已有公开符号及组织方式。
def append(text: str, code: str) -> str:
    return text.rstrip() + "\n\n" + code.strip() + "\n"


# 预览和实施共享同一改动清单，报告仅列真正内容不同的文件。
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


# AST列偏移按UTF8字节计，中文标题不影响登记表达式定位。
def column(line: str, byte_offset: int) -> int:
    return len(line.encode("utf-8")[:byte_offset].decode("utf-8"))


# 新导入放在文档和future声明之后，交给统一格式整理。
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


# 后处理文档目标列入文件清单；本机汇总文件单独生成，不计入Git影响范围。
def snapshot(paths: list[Path]) -> dict[Path, str | None]:
    return {path: path.read_text() if path.exists() else None for path in paths}
