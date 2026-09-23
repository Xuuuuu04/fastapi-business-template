"""
检查关键层级不反向导入具体实现。
静态检查覆盖常规导入，不把 Python 当作安全隔离环境。
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# 读取普通导入与 from 导入涉及的模块。
def imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


# 验证共享层、接口路由和业务规则的依赖方向。
def test_layer_imports() -> None:
    for path in (ROOT / "shared").rglob("*.py"):
        assert not any(name.startswith(("app", "service")) for name in imports(path)), path
    for path in (ROOT / "app/api/routes").rglob("*.py"):
        assert not any(name.startswith("app.setup") for name in imports(path)), path
        assert not any(
            name.startswith("service.") and not name.endswith((".public", ".types"))
            for name in imports(path)
        ), path
    for path in (ROOT / "service/notes").glob("*.py"):
        assert not any(
            name.startswith(("app", "fastapi", "sqlite3", "shared", "service.notes.store"))
            for name in imports(path)
        ), path


# 禁止业务包直接导入其他业务包的实现。
def test_feature_imports() -> None:
    for path in (ROOT / "service").rglob("*.py"):
        feature = path.relative_to(ROOT / "service").parts[0]
        for name in imports(path):
            parts = name.split(".")
            if len(parts) < 2 or parts[0] != "service" or parts[1] == feature:
                continue
            assert name.endswith((".public", ".types")), (path, name)
