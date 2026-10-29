import ast
import re
from pathlib import Path

from fastapi_check.quality.report import Problem, files_under, relative
from fastapi_check.quality.rules import CODE_DIRS, CONDITION_WORDS, ROOT, STEP_VERBS, VAGUE_NAMES

SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def check_naming(root: Path = ROOT) -> list[Problem]:
    problems = check_paths(root)
    problems += check_module_names(root)
    for path in files_under(root, ("service",), ".py"):
        problems += check_step_names(path, root)
    return problems


def check_paths(root: Path) -> list[Problem]:
    problems = []
    for path in files_under(root, CODE_DIRS, ".py"):
        parts = (
            path.relative_to(root).with_suffix("").parts
            if path.is_relative_to(root)
            else path.relative_to(root.parent / ".agents/skills").with_suffix("").parts[2:]
        )
        for part in parts:
            if part.startswith("test_") and path.parts[-1] == f"{part}.py":
                part = part.removeprefix("test_")
            if not SNAKE.match(part):
                problems.append(
                    Problem(
                        relative(path, root),
                        0,
                        "name_format",
                        f"名字 {part} 应该用小写字母和下划线",
                    )
                )
            elif part in VAGUE_NAMES:
                problems.append(
                    Problem(
                        relative(path, root),
                        0,
                        "name_vague",
                        f"名字 {part} 含义模糊",
                        "用说明用途的名字，例如 read_source、save_result",
                    )
                )
    return sorted(set(problems), key=lambda item: (item.path, item.message))


def check_module_names(root: Path) -> list[Problem]:
    service = root / "service"
    if not service.exists():
        return []
    return [
        Problem(
            f"service/{path.name}",
            0,
            "module_name",
            f"模块名 {path.name} 至少要两个词",
            "例如 order_records、customer_contact，第二个词说明具体做什么",
        )
        for path in sorted(service.iterdir())
        if path.is_dir() and not path.name.startswith(("_", ".")) and len(path.name.split("_")) < 2
    ]


def check_step_names(path: Path, root: Path) -> list[Problem]:
    problems = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        kind = decorator_name(node)
        words = node.name.split("_")
        if kind == "step" and (len(words) < 2 or words[0] not in STEP_VERBS):
            problems.append(
                Problem(
                    relative(path, root),
                    node.lineno,
                    "step_name",
                    f"步骤函数 {node.name} 应写成“动词_对象”",
                    f"动词从这些里选：{', '.join(sorted(STEP_VERBS))}",
                )
            )
        if kind == "condition" and (len(words) < 2 or words[0] not in CONDITION_WORDS):
            problems.append(
                Problem(
                    relative(path, root),
                    node.lineno,
                    "condition_name",
                    f"条件函数 {node.name} 应以 {'、'.join(sorted(CONDITION_WORDS))} 开头",
                )
            )
    return problems


def decorator_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    for item in node.decorator_list:
        target = item.func if isinstance(item, ast.Call) else item
        if isinstance(target, ast.Name) and target.id in ("step", "condition"):
            return target.id
    return ""
