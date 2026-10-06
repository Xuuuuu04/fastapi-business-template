"""
质量检查例外；问题与文件遍历复用运行时检查。
"""

from fastapi_check.quality.rules import ALLOWED

from shared.modules.validation.report import Problem as Problem
from shared.modules.validation.report import files_under as files_under
from shared.modules.validation.report import relative as relative


# 去掉已登记为例外的问题。
def without_allowed(problems: list[Problem]) -> list[Problem]:
    allowed = {(item.path, item.rule) for item in ALLOWED}
    return [problem for problem in problems if (problem.path, problem.rule) not in allowed]


# 找出已经不再需要的例外。
def unused_allowed(problems: list[Problem]) -> list[Problem]:
    found = {(problem.path, problem.rule) for problem in problems}
    return [
        Problem(
            item.path, 0, "unused_exception", f"例外“{item.rule}”已经不再需要", "从 rules.py 删除"
        )
        for item in ALLOWED
        if (item.path, item.rule) not in found
    ]
