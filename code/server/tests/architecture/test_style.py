"""
检查约定的说明格式与关键依赖方向。
避免代码增加后出现缺少说明或业务依赖 HTTP 的情况。
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# 检查每个 Python 文件的头部说明和函数说明。
def test_comments() -> None:
    for folder in ("app", "service", "shared", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            source = path.read_text()
            tree = ast.parse(source)
            assert ast.get_docstring(tree), f"缺少文件说明：{path}"
            assert source.startswith('"""\n'), f"文件说明应为多行：{path}"
            lines = source.splitlines()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                    assert lines[start - 2].lstrip().startswith("# "), (
                        f"缺少函数单行说明：{path}:{node.lineno}"
                    )


# 检查业务规则和数据定义不依赖接口或数据库实现。
def test_dependencies() -> None:
    for path in (ROOT / "service/notes").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(("app", "fastapi", "sqlite3", "shared.db"))
