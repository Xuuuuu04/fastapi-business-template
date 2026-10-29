import ast
import json
import os
import warnings
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from shared.modules.validation.library_rules import check_libraries
from shared.modules.validation.pure import check_pure, direction_problem
from shared.modules.validation.report import ROOT, Problem, files_under, relative

WEB_LIBRARIES = ("fastapi", "starlette", "httpx", "httpx2", "requests", "uvicorn")
DATABASE_LIBRARIES = ("sqlalchemy", "sqlite3", "psycopg", "aiosqlite", "alembic")


def check_imports(root: Path = ROOT, *, strict: bool | None = None) -> list[Problem]:
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
    return migration_policy(problems, strict, root) + check_libraries(root)


def migration_policy(problems: list[Problem], strict: bool | None, root: Path) -> list[Problem]:
    if strict is None:
        strict = os.getenv("APP_MODULE_DEPENDENCIES_STRICT", "false").lower() in {"1", "true"}
    errors = []
    for problem in problems:
        if (
            problem.rule == "import_direction"
            and not strict
            and not package_strict(root, problem.path)
        ):
            warnings.warn(
                problem.text() + "；迁移后设置 APP_MODULE_DEPENDENCIES_STRICT=true",
                UserWarning,
                stacklevel=2,
            )
        else:
            errors.append(problem)
    return errors


def package_strict(root: Path, path: str) -> bool:
    parts = Path(path).parts
    if len(parts) < 2 or parts[0] != "service":
        return False
    marker = root / "service" / parts[1] / "module.json"
    try:
        return json.loads(marker.read_text()).get("dependencies") == "strict"
    except (OSError, ValueError, AttributeError):
        return False


def imported(path: Path) -> Iterator[tuple[str, int]]:
    yield from analyzed(path.read_text(encoding="utf-8"))[0]


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


def check_service_file(path: Path, root: Path) -> list[Problem]:
    name = relative(path, root)
    parts = path.relative_to(root / "service").parts
    area = parts[1] if len(parts) > 2 else ""
    problems = []
    for module, line in imported(path):
        found = service_problem(module, parts[0], area)
        if found is not None:
            problems.append(Problem(name, line, *found))
    if area == "calc":
        problems += check_pure(path, root)
    return problems


def service_problem(module: str, own: str, area: str) -> tuple[str, str, str] | None:
    direction = direction_problem(module, own, area)
    if direction:
        return direction
    top = module.split(".")[0]
    if top == "library" and not module.endswith(".public"):
        return "import_library", f"工具引用越过公开入口 {module}", "只导入library.工具包.public"
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


def own_or_public(module: str, own: str) -> bool:
    parts = module.split(".")
    return parts[1] == own or (len(parts) == 3 and parts[2] == "public")


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


def forbid(path: Path, root: Path, tops: tuple[str, ...], message: str) -> list[Problem]:
    return [
        Problem(relative(path, root), line, "import_layer", f"{message}：导入了 {module}")
        for module, line in imported(path)
        if module.split(".")[0] in tops
    ]


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


def call_name(node: ast.Call) -> str:
    target = node.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return f"{target.value.id}.{target.attr}"
    return ""
