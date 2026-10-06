"""
检查依赖方向：
业务模块只从 shared.public 使用框架，只导入其他模块的 public.py；步骤不导入数据库和 HTTP 库；
shared 不导入 app、service、tools；接口层只导入模块的 public.py；
业务和框架代码不用动态导入和相对导入。
"""

import ast
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from shared.modules.validation.report import ROOT, Problem, files_under, relative

WEB_LIBRARIES = ("fastapi", "starlette", "httpx", "httpx2", "requests", "uvicorn")
DATABASE_LIBRARIES = ("sqlalchemy", "sqlite3", "psycopg", "aiosqlite", "alembic")


# 检查全部依赖方向。
def check_imports(root: Path = ROOT) -> list[Problem]:
    problems = []
    for path in files_under(root, ("service",), ".py"):
        problems += check_service_file(path, root)
    for path in files_under(root, ("shared",), ".py"):
        problems += forbid(
            path,
            root,
            (
                "app",
                "service",
                "tools",
                "tests",
                "fastapi_check",
                "fastapi_docs",
                "fastapi_project",
                "fastapi_module",
                "fastapi_template",
                "fastapi_operations",
                "fastapi_migration",
            ),
            "框架代码不能依赖业务、接口或工具",
        )
    for path in files_under(root, ("app/api",), ".py"):
        problems += check_api_file(path, root)
    for path in files_under(root, ("service", "shared", "app"), ".py"):
        problems += check_dynamic(path, root)
    return problems


# 列出一个文件导入的全部模块名和行号；相对导入的名称以点开头。
def imported(path: Path) -> Iterator[tuple[str, int]]:
    yield from analyzed(path.read_text(encoding="utf-8"))[0]


# 按实际内容缓存不可变结果，每次仍读取文件；不依赖时间戳，也不缓存检查结论。
@lru_cache(maxsize=4096)
def analyzed(source: str) -> tuple[tuple[tuple[str, int], ...], tuple[int, ...]]:
    imports = []
    dynamic = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            if module.startswith("service.") and module.count(".") == 1:
                for alias in node.names:
                    imports.append((f"{module}.{alias.name}", node.lineno))
            else:
                imports.append((module, node.lineno))
        elif isinstance(node, ast.Call) and call_name(node) in (
            "importlib.import_module",
            "__import__",
        ):
            dynamic.append(node.lineno)
    return tuple(imports), tuple(dynamic)


# 检查业务模块中的一个文件。
def check_service_file(path: Path, root: Path) -> list[Problem]:
    name = relative(path, root)
    parts = path.relative_to(root / "service").parts
    area = parts[1] if len(parts) > 2 else ""
    problems = []
    for module, line in imported(path):
        found = service_problem(module, parts[0], area)
        if found is not None:
            problems.append(Problem(name, line, *found))
    return problems


# 判断业务代码的一条导入是否越界，返回规则、说明和建议。
def service_problem(module: str, own: str, area: str) -> tuple[str, str, str] | None:
    top = module.split(".")[0]
    if module.startswith("shared") and module != "shared.public":
        return "import_shared", f"业务代码导入了 {module}", "框架功能统一从 shared.public 导入"
    if top in (
        "app",
        "tools",
        "tests",
        "fastapi_check",
        "fastapi_docs",
        "fastapi_project",
        "fastapi_module",
        "fastapi_template",
        "fastapi_operations",
        "fastapi_migration",
    ):
        return "import_layer", f"业务代码导入了 {module}", "业务模块不能依赖接口层和工具"
    if top in WEB_LIBRARIES:
        return "import_web", f"业务代码导入了 {module}", "HTTP 处理放在 app/api"
    if top in DATABASE_LIBRARIES and area != "store":
        hint = "数据库访问放在 store/，步骤通过 store 参数使用"
        return "import_database", f"{module} 只能在 store/ 中使用", hint
    if module.startswith("service.") and not own_or_public(module, own):
        hint = "只能导入 service.模块名.public"
        return "import_module", f"导入了其他模块的内部文件 {module}", hint
    return None


# 判断导入的是本模块的文件，或其他模块的 public.py。
def own_or_public(module: str, own: str) -> bool:
    parts = module.split(".")
    return parts[1] == own or (len(parts) == 3 and parts[2] == "public")


# 检查接口层文件：只能导入模块的 public.py。
def check_api_file(path: Path, root: Path) -> list[Problem]:
    name = relative(path, root)
    return [
        Problem(
            name,
            line,
            "import_module",
            f"接口层导入了模块内部文件 {module}",
            "只能导入 service.模块名.public",
        )
        for module, line in imported(path)
        if module.startswith("service.") and not module.endswith(".public")
    ]


# 禁止导入某些顶层包。
def forbid(path: Path, root: Path, tops: tuple[str, ...], message: str) -> list[Problem]:
    return [
        Problem(relative(path, root), line, "import_layer", f"{message}：导入了 {module}")
        for module, line in imported(path)
        if module.split(".")[0] in tops
    ]


# 禁止动态导入和相对导入，依赖关系必须能从源码直接看出。
def check_dynamic(path: Path, root: Path) -> list[Problem]:
    name = relative(path, root)
    problems = [
        Problem(name, line, "import_relative", f"使用了相对导入 {module}", "写完整的模块路径")
        for module, line in imported(path)
        if module.startswith(".")
    ]
    for line in analyzed(path.read_text(encoding="utf-8"))[1]:
        problems.append(
            Problem(name, line, "import_dynamic", "使用了动态导入", "直接写 import 语句")
        )
    return problems


# 取得函数调用的名称，例如 importlib.import_module。
def call_name(node: ast.Call) -> str:
    target = node.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return f"{target.value.id}.{target.attr}"
    return ""
