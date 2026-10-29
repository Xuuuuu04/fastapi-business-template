from collections.abc import Sequence

from fastapi_check.quality.rules import ALLOWED

from shared.modules.validation.report import Problem as Problem
from shared.modules.validation.report import files_under as files_under
from shared.modules.validation.report import relative as relative


def without_allowed(problems: list[Problem]) -> list[Problem]:
    allowed = {(item.path, item.rule) for item in ALLOWED}
    return [problem for problem in problems if (problem.path, problem.rule) not in allowed]


def unused_allowed(problems: list[Problem]) -> list[Problem]:
    found = {(problem.path, problem.rule) for problem in problems}
    return [
        Problem(
            item.path, 0, "unused_exception", f"例外“{item.rule}”已经不再需要", "从 rules.py 删除"
        )
        for item in ALLOWED
        if (item.path, item.rule) not in found
    ]


def in_modules(problems: list[Problem], names: Sequence[str]) -> list[Problem]:
    if not names:
        return problems
    from fastapi_check.affected.selection import module_files

    files = set(module_files(tuple(names)))
    folders = [
        f"{base}/{name}"
        for name in names
        for base in ("service", "tests/modules", "tests/integration", "doc")
    ]

    def owned(path: str) -> bool:
        path = path.removeprefix("server/")
        return path in files or any(path == item or path.startswith(item + "/") for item in folders)

    return [problem for problem in problems if owned(problem.path)]
