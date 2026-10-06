"""
质量问题的统一格式：文件、行号、规则、说明和整理建议。
检查函数只返回问题清单，不修改任何文件。
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP_PARTS = ("__pycache__", ".venv", "versions", "temp")


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
        base = (root / folder).resolve()
        if not base.exists():
            continue
        for path in sorted(base.rglob(f"*{suffix}")):
            if not any(part in SKIP_PARTS for part in path.parts):
                yield path
