import ast
from pathlib import Path

from shared.modules.validation.report import Problem, relative

PURE_LIBRARIES = {
    "__future__",
    "typing",
    "collections",
    "dataclasses",
    "decimal",
    "fractions",
    "math",
    "re",
    "statistics",
    "functools",
    "itertools",
    "operator",
    "enum",
    "string",
    "bisect",
    "heapq",
    "datetime",
}
PURE_PUBLIC = {"Data", "WorkData", "meaning", "BusinessError", "Kind", "ExactNumber", "UtcTime"}
FORBIDDEN_CALLS = {
    "open",
    "input",
    "print",
    "eval",
    "exec",
    "__import__",
    "breakpoint",
    "getattr",
    "setattr",
    "globals",
    "locals",
}
CLOCK_CALLS = {"now", "utcnow", "today"}
EFFECT_NAMES = {"db", "store", "session", "connection", "remote", "files", "client"}
FILE_CALLS = {"read_text", "write_text", "read_bytes", "write_bytes", "open"}


def direction_problem(module: str, own: str, area: str) -> tuple[str, str, str] | None:
    prefix = f"service.{own}."
    if area == "store" and module.startswith("service.") and not module.startswith(prefix):
        return (
            "import_direction",
            f"store/ 导入了 {module}",
            "跨模块操作放到步骤，纯计算只复用本包 calc",
        )
    if not module.startswith(prefix):
        return None
    target = module[len(prefix) :]
    if area == "calc" and not (target == "calc" or target.startswith("calc.")):
        return "calc_dependency", f"纯计算导入了 {module}", "只接收参数；业务数据由步骤传入"
    allowed = ("store", "calc") if area == "store" else ("steps", "calc", "data")
    if area == "steps" and target == "store.contract":
        return None
    if area in {"store", "steps"} and not any(
        target == name
        or target.startswith(name + ".")
        or (name == "data" and target.startswith("data_"))
        for name in allowed
    ):
        return (
            "import_direction",
            f"{area}/ 反向导入了 {module}",
            ("公共计算移到 calc/；数据通过参数传入；步骤只导入 store.contract，不导入存储实现"),
        )
    return None


def check_pure(path: Path, root: Path) -> list[Problem]:
    tree = ast.parse(path.read_text())
    aliases: dict[str, str] = {}
    problems = []
    nodes = list(ast.walk(tree))
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                full = alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}"
                aliases[alias.asname or alias.name.split(".")[0]] = full
                own = (
                    path.relative_to(root).parts[1]
                    if path.relative_to(root).parts[0] == "library"
                    else path.parent.parent.name
                )
                if not pure_import(full, own):
                    problems.append(issue(path, root, node.lineno, f"纯计算导入了 {full}"))
    for node in nodes:
        if isinstance(node, ast.Call):
            name = resolved(node.func, aliases)
            if forbidden(name):
                problems.append(issue(path, root, node.lineno, f"纯计算调用了 {name}"))
    return problems


def pure_import(name: str, own: str) -> bool:
    parts = name.split(".")
    if parts[0] == "library" and len(parts) >= 3:
        return parts[2] == "public" or (parts[1] == own and parts[2] in {"calc", "data"})
    if name.startswith(f"service.{own}.calc."):
        return True
    if name.startswith("shared.public."):
        return name.removeprefix("shared.public.") in PURE_PUBLIC | {"Endpoint", "EndpointReply"}
    return name.split(".")[0] in PURE_LIBRARIES


def resolved(node: ast.expr, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return resolved(node.value, aliases) + "." + node.attr
    return ""


def forbidden(name: str) -> bool:
    return name.removeprefix("builtins.") in FORBIDDEN_CALLS or (
        name.split(".")[-1] in CLOCK_CALLS | FILE_CALLS
        or ("." in name and name.split(".")[0] in EFFECT_NAMES)
    )


def issue(path: Path, root: Path, line: int, message: str) -> Problem:
    return Problem(
        relative(path, root),
        line,
        "calc_purity",
        message,
        "数据库/外部/文件放到 store/；时间和随机值由步骤取得后作为参数传入",
    )
