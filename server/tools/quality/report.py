"""
质量问题的统一格式：文件、行号、规则、说明和整理建议。
检查函数只返回问题清单，不修改任何文件。
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tools.quality.rules import ALLOWED, ROOT, SKIP_PARTS


# 一次规范检查发现的问题，包含文件、位置、原因和处理建议。
@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    rule: str
    message: str
    hint: str = ""

    # 整理成一行便于阅读的文字。
    def text(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        tail = f" 建议：{self.hint}" if self.hint else ""
        return f"{where} [{self.rule}] {self.message}{tail}"


# 把路径写成相对 server/ 的形式。
def relative(path: Path, root: Path = ROOT) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


# 列出目录下需要检查的文件，跳过缓存、虚拟环境、迁移版本和临时目录。
def files_under(root: Path, folders: Iterable[str], suffix: str) -> Iterator[Path]:
    for folder in folders:
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob(f"*{suffix}")):
            if not any(part in SKIP_PARTS for part in path.relative_to(root).parts):
                yield path


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
